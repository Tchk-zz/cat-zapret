"""Deep connectivity checks for Discord (priority) and YouTube via zapret.

A simple ping is not enough to judge a bypass strategy: DPI often lets a
connection open and pass the first packets, then *freezes* it a few seconds
later (throttling). So besides base reachability we measure:

  * freeze test  -- stream data for N seconds; a stall means the strategy only
                    looks like it works.
  * throughput   -- sustained download speed (Mbit/s).
  * stability    -- several probes; how many succeed + jitter.
  * Discord voice-- signaling reachability (HTTPS) plus real UDP capability via
                    a STUN round-trip (a reliable proxy for voice working).

Discord is weighted highest and voice is part of the score.
"""
from __future__ import annotations

import os
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from statistics import pstdev
from typing import List, Optional, Tuple

# Every long-running check accepts an optional ``cancel`` event. Without it a
# user pressing "Отмена" during auto-select had to wait for the current
# freeze window (up to ~16 s) plus the voice probes to finish, which felt like
# the app had hung. With it, each probe loop checks the flag and bails out
# within milliseconds.
CancelEvent = Optional["threading.Event"]


def _cancelled(cancel: CancelEvent) -> bool:
    return cancel is not None and cancel.is_set()

try:
    import requests
except ImportError:  # pragma: no cover - requests is a hard dependency
    requests = None  # type: ignore

try:
    from urllib3.exceptions import ProtocolError as _Urllib3ProtocolError
except ImportError:  # pragma: no cover - urllib3 is bundled with requests
    class _Urllib3ProtocolError(Exception):
        pass

# --- endpoints ------------------------------------------------------------
# Discord first: it is the priority service.
DISCORD_TARGETS: List[str] = [
    "https://discord.com/api/v9/gateway",
    "https://gateway.discord.gg/",
    "https://cdn.discordapp.com/",
]
YOUTUBE_TARGETS: List[str] = [
    "https://www.youtube.com/",
    "https://i.ytimg.com/",
    "https://rr1---sn-4g5e6nzz.googlevideo.com/generate_204",
]

# Public, no-auth assets used for the sustained freeze/throughput test.
DISCORD_STREAM_URLS: List[str] = [
    "https://cdn.discordapp.com/embed/avatars/0.png",
    "https://cdn.discordapp.com/embed/avatars/1.png",
    "https://cdn.discordapp.com/embed/avatars/2.png",
    "https://cdn.discordapp.com/embed/avatars/3.png",
    "https://cdn.discordapp.com/embed/avatars/4.png",
]
YOUTUBE_STREAM_URLS: List[str] = [
    "https://i.ytimg.com/vi/aqz-KE-bpKQ/maxresdefault.jpg",
    "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "https://www.youtube.com/",
]

# STUN servers answer a UDP Binding Request -- used to prove real-time UDP
# (the transport Discord voice relies on) actually works on this connection.
# Multiple providers so a single blocked host doesn't make voice look dead.
STUN_SERVERS: List[Tuple[str, int]] = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun.nextcloud.com", 3478),
    ("stun.twilio.com", 3478),
]


# Upper bound for the extrapolated Chrome major version (see below).
MAX_CHROME_MAJOR = 145


def _build_user_agent() -> str:
    """Build a current-looking desktop Chrome User-Agent string.

    Previously this was hardcoded to ``Chrome/124.0`` (April 2024). Some
    services (notably Cloudflare fronted endpoints) start challenging or
    silently blocking browsers more than ~2 major versions behind current.
    Rather than maintain a hardcoded number that ages, we project a
    plausible Chrome major version from the calendar:

      * Anchor: Chrome 124 was released on 2024-04-23.
      * Cadence: a new Chrome major ships every ~4 weeks (≈ 13/year).

    The projected version is monotonic and matches what a real up-to-date
    Chrome install would report. We cap the patch number at 0 to avoid
    making up spurious CVE numbers; ``Chrome/<major>.0`` is what real
    Chrome reports when patched to the latest major.

    The OS section is intentionally kept Windows-only because the bypass
    engine runs only on Windows anyway; mixing in Linux/macOS tokens would
    be misleading to anti-bot heuristics.
    """
    anchor_date = date(2024, 4, 23)
    anchor_major = 124
    today = date.today()
    # Days since anchor → approximate majors released. ~28 days per major.
    days_since = (today - anchor_date).days
    majors_since = days_since // 28
    chrome_major = max(anchor_major, anchor_major + majors_since)
    # Hard ceiling: extrapolation is only a guess, and on a machine with a
    # wrong (future) system clock it produced absurd versions like Chrome 180,
    # which anti-bot filters flag faster than a slightly old UA. Clamp to a
    # range that stays believable.
    chrome_major = min(chrome_major, MAX_CHROME_MAJOR)
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_major}.0.0.0 Safari/537.36"
    )


_HEADERS = {
    "User-Agent": _build_user_agent(),
}


@dataclass
class CheckResult:
    """Result of a quick base reachability check (also used by the UI button)."""

    youtube: bool
    discord: bool
    detail: str = ""
    yt_ms: float = 0.0
    dc_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.youtube and self.discord

    @property
    def score(self) -> int:
        return (1 if self.youtube else 0) + (1 if self.discord else 0)

    @property
    def latency_ms(self) -> Optional[float]:
        vals = [v for v in (self.yt_ms, self.dc_ms) if v > 0]
        if not vals:
            return None
        return sum(vals) / len(vals)


@dataclass
class DeepResult:
    """Rich result of a deep check, with a Discord-weighted score."""

    youtube: bool
    discord: bool
    discord_freeze_ok: bool
    youtube_freeze_ok: bool
    voice_signaling: bool
    voice_udp: bool
    throughput_mbps: float
    stability: float          # 0..1 fraction of successful Discord probes
    jitter_ms: float
    latency_ms: Optional[float]
    score: float
    detail: str = ""

    @property
    def voice_ok(self) -> bool:
        return self.voice_signaling and self.voice_udp

    @property
    def ok(self) -> bool:
        """Fully usable: Discord reachable, no freeze, voice works."""
        return self.discord and self.discord_freeze_ok and self.voice_ok


# --- low level probes -----------------------------------------------------
def _probe(url: str, timeout: float) -> Tuple[bool, float]:
    """Return (reachable, elapsed_ms) for a single URL."""
    if requests is None:
        return (False, 0.0)
    start = time.monotonic()
    try:
        resp = requests.get(
            url,
            headers=_HEADERS,
            timeout=timeout,
            stream=True,
            allow_redirects=True,
        )
        elapsed = (time.monotonic() - start) * 1000.0
        ok = resp.status_code < 500
        resp.close()
        return (ok, elapsed)
    except Exception:
        return (False, 0.0)


def _probe_set(
    urls: List[str], timeout: float, cancel: CancelEvent = None
) -> Tuple[bool, float]:
    """Reachable if ANY url answers; returns the latency of the fastest hit.

    The probes run in parallel. Sequentially, a fully blocked target cost
    ``len(urls) * timeout`` (up to 18 s per check with a 6 s timeout) even
    though a single answer is enough — that was the main reason auto-select
    took half an hour for some users. In parallel the worst case is one
    ``timeout``.
    """
    if _cancelled(cancel) or not urls:
        return (False, 0.0)
    best_ms = 0.0
    found = False
    with ThreadPoolExecutor(max_workers=len(urls)) as pool:
        futures = [pool.submit(_probe, u, timeout) for u in urls]
        for fut in futures:
            try:
                ok, ms = fut.result()
            except Exception:  # noqa: BLE001
                continue
            if ok and (not found or (0 < ms < best_ms) or best_ms == 0.0):
                found = True
                best_ms = ms
    return (found, best_ms if found else 0.0)


def _freeze_test(
    urls: List[str],
    connect_timeout: float,
    duration: float,
    stall_timeout: float,
    cancel: CancelEvent = None,
) -> Tuple[bool, float, bool]:
    """Stream data for ``duration`` seconds and watch for a mid-stream stall.

    Returns (no_freeze, throughput_mbps, reached).
      * no_freeze -- True if data kept flowing without a stall for the window.
      * reached   -- True if we managed to connect at least once.
    Small assets are requested repeatedly to keep the path busy for the whole
    window, so DPI that throttles after a few seconds is still caught.
    """
    if requests is None:
        return (False, 0.0, False)
    reached = False
    froze = False
    total_bytes = 0
    start = time.monotonic()
    i = 0
    while time.monotonic() - start < duration:
        if _cancelled(cancel):
            break
        url = urls[i % len(urls)]
        i += 1
        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                timeout=(connect_timeout, stall_timeout),
                stream=True,
                allow_redirects=True,
            )
            reached = True
            for chunk in resp.iter_content(8192):
                total_bytes += len(chunk)
                # Checked per chunk so "Отмена" interrupts even a long
                # in-flight download instead of waiting out the window.
                if _cancelled(cancel) or time.monotonic() - start >= duration:
                    break
            resp.close()
        except requests.exceptions.ReadTimeout:
            # Connected, then data stopped arriving -> classic DPI freeze.
            froze = True
            break
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                _Urllib3ProtocolError):
            # Many DPI middleboxes don't stall cleanly — they RST the stream
            # mid-transfer. After a successful `reached`, treat that as a
            # freeze too, otherwise DPI strategies that reset connections look
            # healthier than they really are.
            if reached:
                froze = True
                break
            # Never even connected; not a freeze, just unreachable.
            break
        except Exception:
            if not reached:
                # Never even connected; not a freeze, just unreachable.
                break
            # Transient hiccup after a good start; keep trying within window.
            continue
    elapsed = max(time.monotonic() - start, 0.001)
    mbps = (total_bytes * 8.0) / elapsed / 1_000_000.0
    return (reached and not froze, mbps, reached)


def _stun_udp_ok(timeout: float = 3.0, cancel: CancelEvent = None) -> bool:
    """Send a STUN Binding Request over UDP; True if a server replies.

    This proves real-time UDP traffic (what Discord voice uses) can leave the
    machine and come back -- a reliable proxy for voice being usable.
    """
    for host, port in STUN_SERVERS:
        if _cancelled(cancel):
            return False
        sock = None
        try:
            txid = os.urandom(12)
            packet = struct.pack(">HHI", 0x0001, 0x0000, 0x2112A442) + txid
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(packet, (host, port))
            data, _ = sock.recvfrom(2048)
            if len(data) >= 2 and struct.unpack(">H", data[:2])[0] == 0x0101:
                return True
        except Exception:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    return False


def _voice_signaling_ok(timeout: float, cancel: CancelEvent = None) -> bool:
    """Discord voice signaling travels over the gateway -- check it answers."""
    ok, _ = _probe_set(
        ["https://gateway.discord.gg/", "https://discord.com/api/v9/gateway"],
        timeout,
        cancel,
    )
    return ok


# --- public checks --------------------------------------------------------
def check(timeout: float = 6.0, cancel: CancelEvent = None) -> CheckResult:
    """Quick base availability of YouTube and Discord (used by the UI button).

    Discord and YouTube are probed concurrently: they are independent, and
    doing them one after another doubled the cost of every quick-filter pass
    in auto-select for no benefit.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_dc = pool.submit(_probe_set, DISCORD_TARGETS, timeout, cancel)
        f_yt = pool.submit(_probe_set, YOUTUBE_TARGETS, timeout, cancel)
        dc, dc_ms = f_dc.result()
        yt, yt_ms = f_yt.result()
    detail = f"YouTube={'OK' if yt else 'FAIL'} Discord={'OK' if dc else 'FAIL'}"
    return CheckResult(youtube=yt, discord=dc, detail=detail, yt_ms=yt_ms, dc_ms=dc_ms)


def check_services(timeout: float = 6.0) -> Tuple[bool, bool]:
    r = check(timeout)
    return r.youtube, r.discord


def deep_check(
    timeout: float = 6.0,
    freeze_seconds: float = 16.0,
    attempts: int = 3,
    enable_voice: bool = True,
    stall_timeout: float = 4.0,
    cancel: CancelEvent = None,
) -> DeepResult:
    """Run the full battery of checks and compute a Discord-weighted score.

    Performance notes (auto-select used to take up to ~30 min on some
    machines, all of it spent here):
      * base Discord/YouTube reachability is probed concurrently;
      * if Discord is completely unreachable the strategy cannot win, so the
        expensive freeze/throughput/voice battery is skipped entirely;
      * the two freeze windows and the voice probes run concurrently instead
        of back-to-back, cutting the per-strategy cost roughly in half.
    ``cancel`` is honoured between (and inside) every stage.
    """
    # Base reachability, in parallel.
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_dc = pool.submit(_probe_set, DISCORD_TARGETS, timeout, cancel)
        f_yt = pool.submit(_probe_set, YOUTUBE_TARGETS, timeout, cancel)
        dc, dc_ms = f_dc.result()
        yt, yt_ms = f_yt.result()

    denom = max(attempts, 1)

    def _empty(detail: str) -> DeepResult:
        return DeepResult(
            youtube=yt, discord=dc, discord_freeze_ok=False,
            youtube_freeze_ok=False, voice_signaling=False, voice_udp=False,
            throughput_mbps=0.0, stability=0.0, jitter_ms=0.0,
            latency_ms=dc_ms or None, score=(6.0 if yt else 0.0), detail=detail,
        )

    if _cancelled(cancel):
        return _empty("отменено")

    if not dc:
        # Discord unreachable => this strategy can never be "ok" and its score
        # would be dominated by the Discord terms anyway. Bail out now instead
        # of burning freeze_seconds + voice timeouts on a hopeless candidate.
        return _empty(
            f"Discord ✗, проверка прервана, YouTube {'✓' if yt else '✗'}"
        )

    # Stability: repeated Discord probes -> success rate + jitter.
    oks = 1 if dc else 0
    lats: List[float] = [dc_ms] if (dc and dc_ms > 0) else []
    for _ in range(max(attempts - 1, 0)):
        if _cancelled(cancel):
            break
        o, ms = _probe_set(DISCORD_TARGETS, timeout, cancel)
        if o:
            oks += 1
            if ms > 0:
                lats.append(ms)
    stability = oks / denom
    jitter = pstdev(lats) if len(lats) >= 2 else 0.0
    latency = (sum(lats) / len(lats)) if lats else (dc_ms or None)

    if _cancelled(cancel):
        return _empty("отменено")

    # Freeze + throughput + voice, all concurrently. Discord gets the full
    # window; YouTube a shorter one.
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_dcf = pool.submit(
            _freeze_test, DISCORD_STREAM_URLS, timeout, freeze_seconds,
            stall_timeout, cancel,
        )
        f_ytf = pool.submit(
            _freeze_test, YOUTUBE_STREAM_URLS, timeout,
            max(freeze_seconds * 0.5, 5.0), stall_timeout, cancel,
        )
        if enable_voice:
            f_sig = pool.submit(_voice_signaling_ok, timeout, cancel)
            f_udp = pool.submit(_stun_udp_ok, min(timeout, 4.0), cancel)
        else:
            f_sig = f_udp = None
        dc_freeze, dc_mbps, _dc_reach = f_dcf.result()
        yt_freeze, yt_mbps, _yt_reach = f_ytf.result()
        if f_sig is not None and f_udp is not None:
            v_sig = f_sig.result()
            v_udp = f_udp.result()
        else:
            v_sig = dc
            v_udp = True
    throughput = max(dc_mbps, yt_mbps)

    if _cancelled(cancel):
        return _empty("отменено")

    # --- weighted score (Discord-centric, voice mandatory) ----------------
    score = 0.0
    if dc:
        score += 30.0
    if dc_freeze:
        score += 25.0
    if enable_voice:
        if v_sig:
            score += 10.0
        if v_udp:
            score += 12.0
    else:
        score += 22.0
    score += stability * 10.0
    if yt:
        score += 6.0
    if yt_freeze:
        score += 3.0
    score += min(throughput / 10.0, 1.0) * 6.0
    if latency:
        score += max(0.0, 1.0 - min(latency, 1000.0) / 1000.0) * 3.0

    voice_txt = "✓" if (v_sig and v_udp) else ("частично" if (v_sig or v_udp) else "✗")
    detail = (
        f"Discord {'✓' if dc else '✗'}"
        f", голос {voice_txt}"
        f", {'без фриза' if dc_freeze else 'фриз!'}"
        f", {throughput:.1f} Мбит/с"
        f", стаб. {oks}/{denom}"
        f", YouTube {'✓' if yt else '✗'}"
    )

    return DeepResult(
        youtube=yt,
        discord=dc,
        discord_freeze_ok=dc_freeze,
        youtube_freeze_ok=yt_freeze,
        voice_signaling=v_sig,
        voice_udp=v_udp,
        throughput_mbps=throughput,
        stability=stability,
        jitter_ms=jitter,
        latency_ms=latency,
        score=score,
        detail=detail,
    )
