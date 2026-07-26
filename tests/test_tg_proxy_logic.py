"""Telegram MTProto proxy: config, runner lifecycle, log dedupe, DC IPs."""
from pathlib import Path
import tempfile
import unittest


class TgProxyLogicTests(unittest.TestCase):

    def _tg_runner_on_free_port(self, data_dir):
        """Create TGProxyRunner configured to a free local port for tests."""
        import socket
        from app import tg_proxy
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        cfg = tg_proxy.read_config(Path(data_dir))
        cfg.port = port
        tg_proxy._save_config(Path(data_dir), cfg)
        return tg_proxy.TGProxyRunner(Path(data_dir))

    def test_tg_proxy_link_format(self):
        """The tg://proxy URL must contain host, port and secret."""
        from app.tg_proxy import TGProxyConfig, proxy_link
        cfg = TGProxyConfig(host="127.0.0.1", port=1443, secret="abc123")
        link = proxy_link(cfg)
        self.assertEqual(link, "tg://proxy?server=127.0.0.1&port=1443&secret=abc123")

    def test_tg_proxy_link_empty_when_no_secret(self):
        from app.tg_proxy import TGProxyConfig, proxy_link
        self.assertEqual(proxy_link(TGProxyConfig(secret="")), "")

    def test_tg_proxy_read_config_generates_secret_on_first_run(self):
        """When no config exists, read_config auto-generates a stable secret
        and persists it. Subsequent reads return the SAME secret."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import read_config, DEFAULT_HOST, DEFAULT_PORT
            cfg1 = read_config(Path(td))
            self.assertEqual(cfg1.host, DEFAULT_HOST)
            self.assertEqual(cfg1.port, DEFAULT_PORT)
            # Secret is auto-generated (32 hex chars).
            self.assertEqual(len(cfg1.secret), 32)
            int(cfg1.secret, 16)  # must be valid hex
            # Second read returns the SAME persisted secret.
            cfg2 = read_config(Path(td))
            self.assertEqual(cfg1.secret, cfg2.secret)

    def test_tg_proxy_read_config_parses_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tgdir = root / "tg-ws-proxy"
            tgdir.mkdir()
            (tgdir / "tg_proxy_config.json").write_text(
                '{"host": "0.0.0.0", "port": 8080, "secret": "0123456789abcdef0123456789abcdef"}',
                encoding="utf-8",
            )
            from app.tg_proxy import read_config
            cfg = read_config(root)
            self.assertEqual(cfg.host, "0.0.0.0")
            self.assertEqual(cfg.port, 8080)
            self.assertEqual(cfg.secret, "0123456789abcdef0123456789abcdef")

    def test_tg_proxy_read_config_repairs_invalid_port_and_secret(self):
        """Hand-edited TG config must never crash the engine: an invalid
        port or non-32-hex secret is repaired before bytes.fromhex()."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tgdir = root / "tg-ws-proxy"
            tgdir.mkdir()
            (tgdir / "tg_proxy_config.json").write_text(
                '{"host": "127.0.0.1", "port": 70000, "secret": "not_hex"}',
                encoding="utf-8",
            )
            from app.tg_proxy import read_config, DEFAULT_PORT
            cfg = read_config(root)
            self.assertEqual(cfg.port, DEFAULT_PORT)
            self.assertEqual(len(cfg.secret), 32)
            int(cfg.secret, 16)

    def test_tg_proxy_read_config_handles_bad_json(self):
        """Bad JSON falls back to a freshly generated config."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tgdir = root / "tg-ws-proxy"
            tgdir.mkdir()
            (tgdir / "tg_proxy_config.json").write_text("not json", encoding="utf-8")
            from app.tg_proxy import read_config, DEFAULT_HOST
            cfg = read_config(root)
            self.assertEqual(cfg.host, DEFAULT_HOST)
            # Secret is auto-regenerated.
            self.assertEqual(len(cfg.secret), 32)

    def test_tg_proxy_is_installed_always_true(self):
        """The proxy engine is embedded as Python — always 'installed'."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import is_installed
            self.assertTrue(is_installed(Path(td)))

    def test_tg_proxy_local_version_returns_embedded_version(self):
        from app.tg_proxy import local_version
        v = local_version(Path("."))
        # Should be a non-empty version string like "1.7.3".
        self.assertTrue(v and v[0].isdigit())

    def test_tg_proxy_ensure_installed_returns_ok(self):
        """ensure_installed is a no-op now (engine is embedded)."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import ensure_installed
            self.assertEqual(ensure_installed(Path(td)), "ok")

    def test_tg_proxy_runner_start_stop_works(self):
        """Smoke test: starting and stopping the runner doesn't crash, and
        is_running() reflects the state. We don't actually verify the engine
        listens on the port (that needs a real network + cryptography), only
        that the lifecycle is correct."""
        with tempfile.TemporaryDirectory() as td:
            r = self._tg_runner_on_free_port(Path(td))
            self.assertFalse(r.is_running())
            try:
                r.start()
                # Give the thread a moment to spin up.
                import time as _t
                _t.sleep(0.3)
                self.assertTrue(r.is_running())
            finally:
                r.stop()
            # After stop, is_running returns False (within 5s grace).
            import time as _t
            _t.sleep(0.2)
            self.assertFalse(r.is_running())

    def test_tg_proxy_runner_stop_is_non_blocking(self):
        """stop() must return almost immediately, NOT block the caller for 5s.
        Previously stop() called thread.join(timeout=5.0) synchronously and
        froze the GUI. Now it spawns a daemon 'joiner' thread."""
        import time as _t
        with tempfile.TemporaryDirectory() as td:
            r = self._tg_runner_on_free_port(Path(td))
            r.start()
            _t.sleep(0.3)  # let it spin up
            t0 = _t.monotonic()
            r.stop()
            elapsed = _t.monotonic() - t0
            # stop() should return in well under 1 second — it just signals
            # the engine and returns. The actual thread join happens in the
            # background daemon.
            self.assertLess(elapsed, 1.0,
                            f"stop() blocked for {elapsed:.2f}s — should be non-blocking")
            # is_running() must immediately report False.
            self.assertFalse(r.is_running())
            # Cleanly wait for the background thread to finish so we don't
            # leak threads into other tests.
            r.wait_for_stop(timeout=6.0)

    def test_tg_proxy_runner_restart_after_stop_does_not_lose_state(self):
        """Race condition regression: rapid stop+start must NOT let the old
        engine's finally block clobber the new engine's _loop/_stop_event.

        Previously the finally block unconditionally set self._loop = None,
        so a new engine that started before the old one's cleanup finished
        would lose its loop reference — the runner thought the proxy was off
        while the engine was actually running. The fix captures the loop
        locally and only clears shared state if THIS thread still owns it.
        """
        import time as _t
        with tempfile.TemporaryDirectory() as td:
            r = self._tg_runner_on_free_port(Path(td))
            r.start()
            _t.sleep(0.3)
            self.assertTrue(r.is_running())
            # Stop, then immediately start again — no wait_for_stop in
            # between, so the old engine's thread is still winding down.
            r.stop()
            r.start()
            _t.sleep(0.5)  # let both threads settle
            # The new engine must be in charge: is_running True, _loop set.
            self.assertTrue(r.is_running(),
                            "New engine lost state — old thread's finally clobbered it")
            self.assertIsNotNone(r._loop,
                                 "self._loop was wiped by the old engine's cleanup")
            self.assertIsNotNone(r._stop_event,
                                 "self._stop_event was wiped by the old engine's cleanup")
            # And we must be able to stop the new engine cleanly.
            r.stop()
            r.wait_for_stop(timeout=6.0)
            self.assertFalse(r.is_running())

    def test_tg_proxy_runner_can_start_after_stop_completes(self):
        """After wait_for_stop, a fresh start must succeed and is_running
        must report True. This is the happy path used by tg_rotate_secret."""
        import time as _t
        with tempfile.TemporaryDirectory() as td:
            r = self._tg_runner_on_free_port(Path(td))
            r.start()
            _t.sleep(0.3)
            r.stop()
            r.wait_for_stop(timeout=6.0)
            self.assertFalse(r.is_running())
            # Now restart cleanly.
            r.start()
            _t.sleep(0.3)
            self.assertTrue(r.is_running())
            r.stop()
            r.wait_for_stop(timeout=6.0)

    def test_tg_proxy_regenerate_secret_creates_new_secret(self):
        """regenerate_secret() must produce a DIFFERENT secret and persist it."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import read_config, regenerate_secret
            cfg_before = read_config(Path(td))
            old_secret = cfg_before.secret
            self.assertEqual(len(old_secret), 32)
            # Rotate.
            cfg_after = regenerate_secret(Path(td))
            self.assertEqual(len(cfg_after.secret), 32)
            self.assertNotEqual(old_secret, cfg_after.secret)
            # Must be persisted — re-reading returns the new secret.
            cfg_reloaded = read_config(Path(td))
            self.assertEqual(cfg_reloaded.secret, cfg_after.secret)

    def test_tg_proxy_proxy_link_changes_after_rotate(self):
        """The tg:// link must reflect the new secret after rotation."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import proxy_link, read_config, regenerate_secret
            link_before = proxy_link(read_config(Path(td)))
            regenerate_secret(Path(td))
            link_after = proxy_link(read_config(Path(td)))
            self.assertNotEqual(link_before, link_after)
            # Both links must contain the secret param.
            self.assertIn("secret=", link_before)
            self.assertIn("secret=", link_after)

    def test_tg_gui_log_deduper_collapses_ws_timeout_progress(self):
        """Direct WS timeout/fronting progress should not spam per localhost port."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        self.assertTrue(d.should_emit('[127.0.0.1:62697] DC203 WS connect timed out via kws2.web.telegram.org')[0])
        self.assertFalse(d.should_emit('[127.0.0.1:62691] DC203 WS connect timed out via kws2.web.telegram.org')[0])
        self.assertTrue(d.should_emit('[127.0.0.1:62695] DC2 -> fronting fallback (Host kws2.web.telegram.org)')[0])
        self.assertFalse(d.should_emit('[127.0.0.1:62696] DC2 -> fronting fallback (Host kws2.web.telegram.org)')[0])

    def test_tg_gui_log_deduper_collapses_fallback_progress_ports(self):
        """Fallback progress debug lines should not flood GUI log per local port."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        self.assertTrue(d.should_emit('[127.0.0.1:56377] DC203 not in config -> fallback')[0])
        self.assertFalse(d.should_emit('[127.0.0.1:56383] DC203 not in config -> fallback')[0])
        self.assertTrue(d.should_emit('[127.0.0.1:56378] DC2 -> trying CF proxy')[0])
        self.assertFalse(d.should_emit('[127.0.0.1:56375] DC2 -> trying CF proxy')[0])

    def test_tg_bad_handshake_logger_is_throttled(self):
        """Wrong-secret handshakes should not spam warning logs per local port."""
        from app.tg_proxy_engine import tg_ws_proxy

        old_last = tg_ws_proxy._last_bad_handshake_log
        old_suppressed = tg_ws_proxy._bad_handshake_suppressed
        try:
            tg_ws_proxy._last_bad_handshake_log = 0.0
            tg_ws_proxy._bad_handshake_suppressed = 0
            with self.assertLogs('tg-mtproto-proxy', level='WARNING') as cm:
                tg_ws_proxy._log_bad_handshake('127.0.0.1:58806')
                tg_ws_proxy._log_bad_handshake('127.0.0.1:58807')
            self.assertEqual(len(cm.output), 1)
            self.assertIn('bad handshake', cm.output[0])
            self.assertEqual(tg_ws_proxy._bad_handshake_suppressed, 1)
        finally:
            tg_ws_proxy._last_bad_handshake_log = old_last
            tg_ws_proxy._bad_handshake_suppressed = old_suppressed

    def test_tg_gui_log_deduper_collapses_bad_handshake_ports(self):
        """Runtime engines with old bad-handshake warning text are deduped too."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        self.assertTrue(d.should_emit('[127.0.0.1:58806] bad handshake (wrong secret or proto)')[0])
        self.assertFalse(d.should_emit('[127.0.0.1:58807] bad handshake (wrong secret or proto)')[0])

    def test_tg_cf_balancer_skips_domain_on_cooldown(self):
        """429/timeout mitigation: failed CF domains should be skipped temporarily."""
        import time
        from app.tg_proxy_engine.balancer import _Balancer

        b = _Balancer()
        b.update_domains_list(["a.example", "b.example"])
        self.assertIn("a.example", list(b.get_domains_for_dc(2)))
        b.mark_domain_failed(2, "a.example", 60.0)
        domains = list(b.get_domains_for_dc(2))
        self.assertNotIn("a.example", domains)
        self.assertIn("b.example", domains)
        self.assertEqual(b.cooldown_count(2), 1)
        # Expire cooldown manually to avoid sleeping.
        b._cooldown_until[(2, "a.example")] = time.monotonic() - 1
        self.assertIn("a.example", list(b.get_domains_for_dc(2)))

    def test_tg_cf_failure_cooldown_429_is_longer_than_timeout(self):
        """HTTP 429 should back off longer than ordinary transient timeouts."""
        from app.tg_proxy_engine.bridge import _cf_failure_cooldown
        from app.tg_proxy_engine.raw_websocket import WsHandshakeError

        self.assertGreaterEqual(_cf_failure_cooldown(WsHandshakeError(429, "HTTP/1.1 429 Too Many Requests")), 600.0)
        self.assertLess(_cf_failure_cooldown(TimeoutError()), 600.0)

    def test_tg_gui_log_deduper_collapses_cf_429_ports(self):
        """Repeated CF 429 lines with different local ports must not flood GUI log."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        ok1, msg1 = d.should_emit("[127.0.0.1:50013] DC2 CF proxy failed: WsHandshakeError('HTTP 429: HTTP/1.1 429 Too Many Requests')")
        ok2, msg2 = d.should_emit("[127.0.0.1:50191] DC2 CF proxy failed: WsHandshakeError('HTTP 429: HTTP/1.1 429 Too Many Requests')")
        self.assertTrue(ok1)
        self.assertIn("похожие ошибки", msg1)
        self.assertFalse(ok2)
        self.assertEqual(msg2, "")

    def test_tg_gui_log_deduper_collapses_timeout_ports(self):
        """Repeated CF TimeoutError lines should be throttled per normalized message."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        self.assertTrue(d.should_emit("[127.0.0.1:50097] DC203 CF proxy failed: TimeoutError()")[0])
        self.assertFalse(d.should_emit("[127.0.0.1:50018] DC203 CF proxy failed: TimeoutError()")[0])

    def test_tg_gui_log_deduper_collapses_no_fallback(self):
        """No-fallback lines are also noisy when CF/TCP fallback is unavailable."""
        from app.tg_proxy import _TGGuiLogDeduper

        d = _TGGuiLogDeduper(min_interval=60.0)
        self.assertTrue(d.should_emit("[127.0.0.1:50178] DC203 no fallback available")[0])
        self.assertFalse(d.should_emit("[127.0.0.1:50179] DC203 no fallback available")[0])

    def test_tg_proxy_update_available_compares_versions(self):
        """update_available() returns None when current == latest, the JSON
        otherwise. We mock latest_release() to control the comparison."""
        from app import tg_proxy
        orig = tg_proxy.latest_release
        try:
            # Case 1: latest == current → None.
            cur = tg_proxy.local_version(Path("."))
            tg_proxy.latest_release = lambda timeout=10.0: {
                "tag_name": "v" + cur,
                "name": "v" + cur,
            }
            self.assertIsNone(tg_proxy.update_available(Path(".")))
            # Case 2: latest > current → returns the JSON.
            tg_proxy.latest_release = lambda timeout=10.0: {
                "tag_name": "v999.999.999",
                "name": "v999.999.999",
            }
            r = tg_proxy.update_available(Path("."))
            self.assertIsNotNone(r)
            self.assertEqual(r["tag_name"], "v999.999.999")
            # Case 3: GitHub unreachable → None.
            tg_proxy.latest_release = lambda timeout=10.0: None
            self.assertIsNone(tg_proxy.update_available(Path(".")))
        finally:
            tg_proxy.latest_release = orig

    def test_tg_proxy_cf_domain_overrides_are_normalized(self):
        from app import tg_proxy
        self.assertEqual(
            tg_proxy._resolve_domains(["Example.COM, worker.example.com", "https://bad.example/x", "example.com"]),
            ["example.com", "worker.example.com"],
        )
        with tempfile.TemporaryDirectory() as td:
            r = tg_proxy.TGProxyRunner(
                Path(td),
                cfproxy_domains=["One.EXAMPLE, two.example"],
                cfworker_domains=["worker.example"],
            )
            self.assertEqual(r.get_cf_domains(), (["one.example", "two.example"], ["worker.example"]))

    def test_tg_proxy_wrapper_disables_forced_ws_keepalive(self):
        """Our wrapper must not re-enable old WS keepalive behavior that
        upstream v1.8.0 rolled back due reports of problems."""
        import asyncio
        from app import tg_proxy
        from app.tg_proxy_engine.config import proxy_config
        with tempfile.TemporaryDirectory() as td:
            r = tg_proxy.TGProxyRunner(Path(td))
            old_run = None
            old = proxy_config.ws_keepalive_interval
            try:
                # Patch engine._run to avoid opening a listening socket here.
                from app.tg_proxy_engine import tg_ws_proxy as engine
                old_run = engine._run
                async def fake_run(stop_event):
                    return None
                engine._run = fake_run
                proxy_config.ws_keepalive_interval = 30.0
                r._cfg = tg_proxy._ensure_config(Path(td))
                asyncio.run(r._run_async(asyncio.Event()))
                self.assertEqual(proxy_config.ws_keepalive_interval, 0.0)
            finally:
                if old_run is not None:
                    engine._run = old_run
                proxy_config.ws_keepalive_interval = old

    def test_tg_proxy_imports_logging_handlers_for_pyinstaller(self):
        """PyInstaller may miss stdlib submodules imported only by the dynamic
        tg-ws-proxy engine. The wrapper must import logging.handlers explicitly
        so frozen builds can import app.tg_proxy_engine.tg_ws_proxy."""
        import logging
        import app.tg_proxy  # noqa: F401
        self.assertTrue(hasattr(logging, "handlers"))

    def test_tg_proxy_engine_importable(self):
        """The embedded engine modules must import cleanly."""
        from app.tg_proxy_engine import tg_ws_proxy, config
        self.assertTrue(hasattr(tg_ws_proxy, "_run"))
        self.assertTrue(hasattr(tg_ws_proxy, "main"))
        self.assertTrue(hasattr(config, "proxy_config"))

    # --- SoundCloud preset test ---

    def test_tg_dc_ip_resolver_keeps_empty_as_empty(self):
        """Empty DC->IP must stay empty for tg-ws-proxy v1.8+.

        Flowseal recommends clearing DC->IP when fronting/WS timeout problems
        happen. Falling back to legacy hardcoded IPs here would defeat that.
        """
        from app import tg_proxy
        self.assertEqual(tg_proxy._resolve_dc_ips(None), [])
        self.assertEqual(tg_proxy._resolve_dc_ips([]), [])

    def test_tg_dc_ip_resolver_filters_invalid_entries(self):
        """Malformed entries (no colon, non-numeric DC, empty IP or invalid
        IP) must be silently dropped before they can crash the engine."""
        from app import tg_proxy
        bad = [
            "not_a_dc_ip",         # no colon
            "abc:1.2.3.4",         # non-numeric DC
            "2:",                  # empty IP
            "6:999.999.999.999",   # invalid IP
            "",                    # empty string
            "  ",                  # whitespace
            "3:149.154.175.100",   # valid
            "5:91.105.192.100",    # valid
        ]
        resolved = tg_proxy._resolve_dc_ips(bad)
        self.assertEqual(resolved, ["3:149.154.175.100", "5:91.105.192.100"])

    def test_tg_effective_dc_redirects_empty_keeps_upstream_fallback(self):
        """Empty TG DC->IP config follows upstream fallback-only behavior."""
        from app import tg_proxy
        from app.tg_proxy_engine.config import parse_dc_ip_list

        self.assertEqual(
            tg_proxy._effective_dc_redirects('app.tg_proxy_engine', parse_dc_ip_list, []),
            {},
        )

    def test_tg_effective_dc_redirects_auto_sentinel_uses_engine_defaults(self):
        """Users can explicitly opt into the built-in DC map with 'auto'."""
        from app import tg_proxy
        from app.tg_proxy_engine.config import parse_dc_ip_list

        redirects = tg_proxy._effective_dc_redirects('app.tg_proxy_engine', parse_dc_ip_list, ['auto'])
        self.assertIn(2, redirects)
        self.assertIn(203, redirects)
        self.assertEqual(redirects[203], '91.105.192.100')

    def test_tg_effective_dc_redirects_fallback_only_sentinel(self):
        """Advanced users can still force fallback-only mode explicitly."""
        from app import tg_proxy
        from app.tg_proxy_engine.config import parse_dc_ip_list

        self.assertEqual(
            tg_proxy._effective_dc_redirects('app.tg_proxy_engine', parse_dc_ip_list, ['fallback-only']),
            {},
        )

    def test_tg_default_dc_ips_matches_upstream_readme_preset(self):
        """UI recommended preset follows Flowseal README troubleshooting advice."""
        from app import tg_proxy
        self.assertEqual(tg_proxy._default_dc_ips(), ['4:149.154.167.220'])

    def test_tg_dc_ip_resolver_all_invalid_returns_empty(self):
        """Invalid DC->IP entries are dropped. If none remain, the result is
        empty, enabling the upstream fallback chain instead of stale IPs."""
        from app import tg_proxy
        bad = ["no_colon", "abc:1.2.3.4", "6:999.999.999.999", ""]
        self.assertEqual(tg_proxy._resolve_dc_ips(bad), [])

    def test_tg_engine_parse_dc_ip_list_rejects_invalid_ipv4(self):
        """socket.inet_aton used to accept abbreviated/odd IPv4 forms;
        ipaddress must reject malformed DC overrides strictly."""
        from app.tg_proxy_engine.config import parse_dc_ip_list
        with self.assertRaises(ValueError):
            parse_dc_ip_list(["6:999.999.999.999"])
        self.assertEqual(parse_dc_ip_list(["3:149.154.175.100"]),
                         {3: "149.154.175.100"})

    def test_tg_runner_set_dc_ips_takes_effect(self):
        """set_dc_ips() must update the runner's stored list so the next
        start() uses the new IPs. get_dc_ips() returns a copy so external
        mutation can't poison the runner's state."""
        with tempfile.TemporaryDirectory() as td:
            from app.tg_proxy import TGProxyRunner
            r = TGProxyRunner(Path(td))
            # Initially empty: this intentionally means no forced DC->IP so
            # tg-ws-proxy v1.8+ can use fronting/CF/direct fallback.
            self.assertEqual(r.get_dc_ips(), [])
            # Update with valid IPs.
            r.set_dc_ips(["3:149.154.175.100", "5:91.105.192.100"])
            self.assertEqual(r.get_dc_ips(),
                             ["3:149.154.175.100", "5:91.105.192.100"])
            # Mutating the returned list must NOT affect the runner.
            lst = r.get_dc_ips()
            lst.append("999.999.999.999")
            self.assertEqual(r.get_dc_ips(),
                             ["3:149.154.175.100", "5:91.105.192.100"])
            # Clearing returns to no forced DC->IP.
            r.set_dc_ips([])
            self.assertEqual(r.get_dc_ips(), [])
            # Cleanup.
            r.stop()
            r.wait_for_stop(timeout=2.0)

    def test_tg_dc_ips_field_in_app_config(self):
        """AppConfig must expose a `tg_proxy_dc_ips` field (list) so the
        GUI can persist user-edited DC IP overrides. Defaults to []."""
        import os
        with tempfile.TemporaryDirectory() as td:
            os.environ["LOCALAPPDATA"] = td
            from app.config import AppConfig
            cfg = AppConfig()
            self.assertEqual(cfg.tg_proxy_dc_ips, [])
            # Must round-trip through save/load.
            cfg.tg_proxy_dc_ips = ["2:149.154.167.99", "4:149.154.167.99"]
            cfg.save()
            cfg2 = AppConfig.load()
            self.assertEqual(cfg2.tg_proxy_dc_ips,
                             ["2:149.154.167.99", "4:149.154.167.99"])

    # --- Zapret list/IPset/HOSTS manager ---

    def test_tg_proxy_update_extracts_runtime_engine_safely(self):
        """tg-ws-proxy update must install proxy/*.py into the writable runtime
        package, skip __init__.py, and update the runtime VERSION marker."""
        import io
        import zipfile
        from app import tg_proxy
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("tg-ws-proxy-1.8.1/proxy/tg_ws_proxy.py", "VALUE = 181\n")
            zf.writestr("tg-ws-proxy-1.8.1/proxy/config.py", "proxy_config = object()\ndef parse_dc_ip_list(x): return {}\n")
            zf.writestr("tg-ws-proxy-1.8.1/proxy/__init__.py", "SHOULD_NOT_COPY = True\n")
            zf.writestr("tg-ws-proxy-1.8.1/LICENSE", "MIT\n")
            zf.writestr("tg-ws-proxy-1.8.1/../escape.py", "bad\n")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = tg_proxy.requests
        try:
            tg_proxy.requests = _Requests()
            with tempfile.TemporaryDirectory() as td:
                data_dir = Path(td)
                rel = tg_proxy.TGProxyReleaseInfo(
                    tag="v1.8.1", name="v1.8.1", zip_url="http://x", html_url="http://y"
                )
                res = tg_proxy.download_and_apply_update(rel, data_dir)
                self.assertTrue(res.ok, res.message)
                runtime = tg_proxy.runtime_engine_dir(data_dir)
                self.assertEqual((runtime / "VERSION").read_text(encoding="utf-8"), "1.8.1")
                self.assertIn("VALUE = 181", (runtime / "tg_ws_proxy.py").read_text(encoding="utf-8"))
                self.assertNotIn("SHOULD_NOT_COPY", (runtime / "__init__.py").read_text(encoding="utf-8"))
                self.assertFalse((Path(td) / "escape.py").exists())
                self.assertEqual(tg_proxy.local_version(data_dir), "1.8.1")
                self.assertEqual(tg_proxy._engine_package_name(data_dir), "tg_proxy_engine_runtime")
        finally:
            tg_proxy.requests = old_requests

    def test_tg_proxy_latest_release_picks_highest_semver(self):
        from app import tg_proxy

        class _Resp:
            def raise_for_status(self):
                return None
            def json(self):
                return [
                    {"tag_name": "v1.7.3", "name": "v1.7.3", "zipball_url": "http://old", "html_url": "http://old"},
                    {"tag_name": "v1.8.1", "name": "v1.8.1", "zipball_url": "http://new", "html_url": "http://new"},
                    {"tag_name": "v1.8.0", "name": "v1.8.0", "zipball_url": "http://mid", "html_url": "http://mid"},
                ]

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = tg_proxy.requests
        try:
            tg_proxy.requests = _Requests()
            rel = tg_proxy.latest_release()
            self.assertEqual(rel.tag, "v1.8.1")
            self.assertEqual(rel.zip_url, "http://new")
        finally:
            tg_proxy.requests = old_requests
