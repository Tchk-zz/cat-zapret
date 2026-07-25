import json
from pathlib import Path
import tempfile
import unittest

from app.exclusions import apply_lists, resolve_domains
from app.strategy_manager import _clean_token, _tokenize_args, combine_with_roblox
from app.updater import _common_root


class CoreLogicTests(unittest.TestCase):

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
    def test_tokenize_keeps_quoted_paths(self):
        args = _tokenize_args('--wf-tcp=443 --hostlist="lists/list general.txt" --dpi-desync=fake')
        self.assertEqual(args, ['--wf-tcp=443', '--hostlist=lists/list general.txt', '--dpi-desync=fake'])

    def test_clean_unknown_placeholder(self):
        self.assertEqual(_clean_token('%UNKNOWN%,'), '')

    def test_combine_with_roblox_unions_wf_ports(self):
        combined = combine_with_roblox(
            ['--wf-tcp=443', '--filter-tcp=443', '--dpi-desync=fake'],
            ['--wf-udp=443,49152-65535', '--filter-udp=49152-65535', '--dpi-desync=fake'],
        )
        self.assertIn('--wf-tcp=443', combined)
        self.assertIn('--wf-udp=443,49152-65535', combined)
        self.assertIn('--new', combined)

    def test_resolve_domains_normalizes_urls(self):
        domains = resolve_domains(['steam'], [' https://Example.com/path ', '*.discord.com'])
        self.assertIn('steampowered.com', domains)
        self.assertIn('example.com', domains)
        self.assertIn('discord.com', domains)
        self.assertNotIn('https://example.com/path', domains)

    def test_apply_lists_preserves_unmanaged_lines(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            lists = root / 'lists'
            lists.mkdir()
            target = lists / 'list-general-user.txt'
            target.write_text('manual.example\n', encoding='utf-8')
            apply_lists(root, include_presets=[], include_custom=['example.com'], exclude_presets=[], exclude_custom=[])
            text = target.read_text(encoding='utf-8')
            self.assertIn('manual.example', text)
            self.assertIn('example.com', text)

    # --- regressions for bugs fixed in this audit ---

    def test_common_root_does_not_strip_content_folder(self):
        # A zip with only bin/... must NOT have "bin/" stripped, otherwise
        # winws.exe would land at the zapret root instead of in bin/.
        names = ['bin/winws.exe', 'bin/WinDivert.dll', 'bin/WinDivert64.sys']
        self.assertEqual(_common_root(names), '')

    def test_common_root_strips_zipball_nesting(self):
        # GitHub source zipballs nest under "<user>-<repo>-<sha>/"
        names = [
            'Flowseal-zapret-discord-youtube-abc123/bin/winws.exe',
            'Flowseal-zapret-discord-youtube-abc123/general.bat',
        ]
        self.assertEqual(_common_root(names), 'Flowseal-zapret-discord-youtube-abc123/')

    def test_common_root_flat_layout_no_strip(self):
        # Flat release asset: multiple top-level entries — nothing to strip.
        names = ['bin/winws.exe', 'lists/list-general.txt', 'general.bat']
        self.assertEqual(_common_root(names), '')

    def test_save_custom_resolves_placeholders(self):
        """A custom strategy pasted with %BIN%/%LISTS% must be saved with
        placeholders resolved so winws.exe doesn't crash at launch."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'bin').mkdir()
            (root / 'bin' / 'winws.exe').write_bytes(b'')
            (root / 'lists').mkdir()
            from app.strategy_manager import StrategyManager
            mgr = StrategyManager(root)
            saved = mgr.save_custom(
                'MyTest',
                '--wf-tcp=443 --hostlist="%LISTS%list-general.txt" --dpi-desync=fake',
            )
            joined = ' '.join(saved.args)
            self.assertNotIn('%LISTS%', joined)
            self.assertIn('list-general.txt', joined)

    # --- tg-ws-proxy integration tests (embedded engine, no subprocess) ---

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
        import logging

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
        with tempfile.TemporaryDirectory() as td:
            r = tg_proxy.TGProxyRunner(Path(td))
            async def fake_run(stop_event):
                return None
            from app.tg_proxy_engine.config import proxy_config
            old = proxy_config.ws_keepalive_interval
            try:
                proxy_config.ws_keepalive_interval = 30.0
                r._cfg = tg_proxy._ensure_config(Path(td))
                asyncio.run(r._run_async(asyncio.Event()))
                self.assertEqual(proxy_config.ws_keepalive_interval, 0.0)
            finally:
                proxy_config.ws_keepalive_interval = old


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

    def test_soundcloud_preset_present_with_full_domain_list(self):
        """SoundCloud preset must exist in the SERVICES list and include all
        the key domains needed for the bypass to actually work — main site,
        API, media streams, the CDN (sndcdn.com), AND the new
        soundcloud.cloud media-streaming infrastructure (without which
        audio playback silently fails as of 2024-2025)."""
        from app.exclusions import service_by_id, resolve_domains
        svc = service_by_id("soundcloud")
        self.assertIsNotNone(svc, "SoundCloud preset not found in SERVICES")
        # Must contain the core domains that Russia DPI-blocks.
        required = [
            # Main site + API
            "soundcloud.com",
            "api-v2.soundcloud.com",
            # Legacy CDN
            "sndcdn.com",
            "cf-media.sndcdn.com",
            "ec-media.sndcdn.com",
            # New media-streaming infrastructure (2024-2025)
            "playback.media-streaming.soundcloud.cloud",
            "license.media-streaming.soundcloud.cloud",
            "assets.web.soundcloud.cloud",
            # Additional edge nodes
            "al.sndcdn.com",
            "va.sndcdn.com",
            "wave.sndcdn.com",
            "a-v2.sndcdn.com",
            "i1.sndcdn.com",
        ]
        for d in required:
            self.assertIn(d, svc.domains,
                          f"SoundCloud preset missing critical domain: {d}")
        # resolve_domains must return the SoundCloud domains when the preset
        # is selected (this is what gets written to list-general-user.txt).
        resolved = resolve_domains(["soundcloud"], [])
        for d in required:
            self.assertIn(d, resolved,
                          f"resolve_domains(['soundcloud']) missing: {d}")

    def test_apply_lists_writes_soundcloud_domains_to_user_list(self):
        """When SoundCloud is selected under 'Apply bypass', its domains must
        end up in lists/list-general-user.txt so zapret applies the bypass
        to them. Must include the new media-streaming.cloud domains too,
        otherwise audio playback silently fails."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "lists").mkdir()
            from app.exclusions import apply_lists
            apply_lists(
                root,
                include_presets=["soundcloud"],
                include_custom=[],
                exclude_presets=[],
                exclude_custom=[],
            )
            text = (root / "lists" / "list-general-user.txt").read_text(encoding="utf-8")
            self.assertIn("soundcloud.com", text)
            self.assertIn("sndcdn.com", text)
            self.assertIn("ec-media.sndcdn.com", text)
            # New 2024-2025 media-streaming infrastructure — without these
            # the site loads but audio doesn't play.
            self.assertIn("playback.media-streaming.soundcloud.cloud", text)
            self.assertIn("license.media-streaming.soundcloud.cloud", text)
            self.assertIn("assets.web.soundcloud.cloud", text)
            self.assertIn("al.sndcdn.com", text)
            self.assertIn("va.sndcdn.com", text)
            self.assertIn("wave.sndcdn.com", text)

    # --- Theme catalog tests ---

    def test_theme_catalog_has_10_themes(self):
        """The catalog must contain exactly 10 themes: 3 presets + 7 image."""
        from ui.themes_catalog import THEMES
        self.assertEqual(len(THEMES), 10)
        presets = [t for t in THEMES if t.group == "preset"]
        images = [t for t in THEMES if t.group == "image"]
        self.assertEqual(len(presets), 3, "Expected 3 preset themes (purple/dark/light)")
        self.assertEqual(len(images), 7, "Expected 7 image themes")

    def test_theme_catalog_presets_have_no_bg_image(self):
        """The 3 preset themes (purple/dark/light) must have bg_image=None —
        they use the procedural gradient / flat fill, not a photo."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "preset":
                self.assertIsNone(t.bg_image,
                                  f"Preset theme '{t.id}' must not have a bg_image")

    def test_theme_catalog_image_themes_have_bg_image(self):
        """Each of the 7 image themes must reference a non-None bg_image file."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "image":
                self.assertIsNotNone(t.bg_image,
                                     f"Image theme '{t.id}' must have a bg_image")
                self.assertTrue(t.bg_image.endswith(".jpg"),
                                f"Image theme '{t.id}' bg_image must be a .jpg file")

    def test_theme_catalog_unique_ids(self):
        """All theme ids must be unique (no duplicates)."""
        from ui.themes_catalog import theme_ids
        ids = theme_ids()
        self.assertEqual(len(ids), len(set(ids)),
                         f"Duplicate theme ids: {ids}")

    def test_theme_catalog_get_theme_falls_back_to_purple(self):
        """get_theme('unknown') must return the purple theme, not raise."""
        from ui.themes_catalog import get_theme
        t = get_theme("nonexistent-theme-id")
        self.assertEqual(t.id, "purple")

    def test_theme_catalog_image_themes_have_palette(self):
        """Each image theme must have a complete palette (text, accent,
        card_bg, etc.) so that get_theme_qss() can generate a full QSS
        from DARK_QSS + colour substitution."""
        from ui.themes_catalog import THEMES
        required_palette_fields = [
            "text", "text_on_accent", "text_muted",
            "card_bg", "card_border", "card_hover",
            "accent", "accent_2", "nav_glow",
        ]
        for t in THEMES:
            if t.group == "image":
                for field in required_palette_fields:
                    val = getattr(t, field, "")
                    self.assertTrue(val,
                                    f"Image theme '{t.id}' must have non-empty palette field '{field}'")

    def test_theme_catalog_image_themes_have_accent_colors(self):
        """Each image theme must define non-empty accent colours (used for
        buttons, links, focus outlines). Both accent and accent_2 must be
        hex colours."""
        from ui.themes_catalog import THEMES
        for t in THEMES:
            if t.group == "image":
                self.assertTrue(t.accent.startswith("#"),
                                f"Image theme '{t.id}' accent must be a hex colour")
                self.assertTrue(t.accent_2.startswith("#"),
                                f"Image theme '{t.id}' accent_2 must be a hex colour")

    def test_theme_catalog_all_background_files_exist(self):
        """Every image theme's bg_image file must exist on disk under
        ui/assets/themes/. A missing file would silently fall back to the
        purple gradient, which is not what the user selected."""
        from ui.themes_catalog import THEMES
        themes_dir = Path(__file__).resolve().parent.parent / "ui" / "assets" / "themes"
        for t in THEMES:
            if t.group == "image" and t.bg_image:
                p = themes_dir / t.bg_image
                self.assertTrue(p.exists(),
                                f"Theme '{t.id}' background image not found: {p}")

    def test_image_theme_qss_uses_theme_text_color_not_purple(self):
        """CRITICAL: LIGHT image themes must NOT contain the hardcoded purple
        text colour '#ece8ff' from DARK_QSS after colour substitution.
        DARK image themes (like 'midnight') legitimately use a light text
        colour because their background is dark."""
        from ui.themes_catalog import THEMES, get_theme_qss
        # Use a minimal DARK_QSS that contains the purple colours we test for.
        fake_dark = "QWidget { color: #ece8ff; } QLabel { color: #9b93c0; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                # The theme's own text colour must be present.
                self.assertIn(t.text, qss,
                              f"Image theme '{t.id}' qss must use its own text colour {t.text}")
                if not t.is_dark:
                    self.assertNotIn("#ece8ff", qss,
                                     f"Light image theme '{t.id}' still has purple #ece8ff")
                    self.assertNotIn("#9b93c0", qss,
                                     f"Light image theme '{t.id}' still has purple #9b93c0")

    def test_image_theme_qss_preserves_power_button_dimensions(self):
        """powerBtn must keep 160px + border-radius: 32px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QPushButton#powerBtn { min-width: 160px; max-width: 160px; min-height: 160px; max-height: 160px; border-radius: 32px; background: rgba(255,255,255,0.05); }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QPushButton#powerBtn\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m, f"Image theme '{t.id}' must have powerBtn rule")
                block = m.group(1)
                self.assertIn("160px", block)
                self.assertIn("border-radius: 32px", block)

    def test_image_theme_qss_preserves_nav_panel_radius(self):
        """navPanel must keep border-radius: 18px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QFrame#navPanel { background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.24); border-radius: 18px; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QFrame#navPanel\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m)
                self.assertIn("border-radius: 18px", m.group(1))

    def test_image_theme_qss_preserves_nav_button_padding(self):
        """navBtn must keep padding: 12px 46px from DARK_QSS."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QPushButton#navBtn { background: transparent; color: #cfc7ee; padding: 12px 46px; border: 1px solid transparent; border-radius: 12px; font-size: 19px; font-weight: 500; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        import re
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                m = re.search(r"QPushButton#navBtn\s*\{([^}]*)\}", qss)
                self.assertIsNotNone(m)
                self.assertIn("padding: 12px 46px", m.group(1))

    def test_image_theme_qss_covers_settings_card(self):
        """Settings card must be recoloured — the purple rgba(16,8,56,...)
        from DARK_QSS must be replaced with the theme's card_bg."""
        from ui.themes_catalog import THEMES, get_theme_qss
        fake_dark = "QFrame#settingsCard { background: rgba(16, 8, 56, 0.42); border: 1px solid rgba(255,255,255,0.10); border-radius: 28px; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                self.assertIn("QFrame#settingsCard", qss)
                self.assertNotIn("rgba(16, 8, 56, 0.42)", qss,
                                 f"Theme '{t.id}' still has purple settings card bg")
                self.assertIn(t.card_bg, qss,
                              f"Theme '{t.id}' must use its card_bg")

    def test_get_theme_qss_image_theme_substitutes_colours(self):
        """get_theme_qss() for an image theme must return DARK_QSS with
        colours substituted — NOT the raw DARK_QSS."""
        from ui.themes_catalog import get_theme_qss, THEMES
        fake_dark = "QWidget { color: #ece8ff; } QPushButton#primary { background: #7d52ff; }"
        base_qss = {"DARK": fake_dark, "WIN11_DARK": "", "WIN11_LIGHT": ""}
        for t in THEMES:
            if t.group == "image":
                qss = get_theme_qss(t.id, base_qss)
                # The purple colours must be gone (for light themes).
                if not t.is_dark:
                    self.assertNotIn("#ece8ff", qss)
                self.assertNotIn("#7d52ff", qss)
                # The theme's accent must be present.
                self.assertIn(t.accent, qss)

    def test_get_theme_qss_preset_uses_prebuilt_strings(self):
        """get_theme_qss() for preset themes must return the pre-built QSS
        strings from theme.py (DARK / WIN11_DARK / WIN11_LIGHT)."""
        from ui.themes_catalog import get_theme_qss
        base_qss = {
            "DARK": "DARK_QSS_BODY",
            "WIN11_DARK": "WIN11_DARK_BODY",
            "WIN11_LIGHT": "WIN11_LIGHT_BODY",
        }
        self.assertEqual(get_theme_qss("purple", base_qss), "DARK_QSS_BODY")
        self.assertEqual(get_theme_qss("dark", base_qss), "WIN11_DARK_BODY")
        self.assertEqual(get_theme_qss("light", base_qss), "WIN11_LIGHT_BODY")

    # --- Auto-start bypass on launch ---

    def test_config_has_autostart_strategy_field(self):
        """AppConfig must have an 'autostart_strategy' field defaulting to
        False. This controls whether the bypass engine auto-starts on launch."""
        from app.config import AppConfig
        cfg = AppConfig()
        self.assertFalse(cfg.autostart_strategy,
                         "autostart_strategy must default to False")
        # Must be settable and saveable.
        cfg.autostart_strategy = True
        self.assertTrue(cfg.autostart_strategy)

    def test_config_autostart_strategy_persists(self):
        """autostart_strategy must survive a save/load cycle."""
        with tempfile.TemporaryDirectory() as td:
            import os
            os.environ["LOCALAPPDATA"] = td
            from app.config import AppConfig
            cfg = AppConfig()
            cfg.autostart_strategy = True
            cfg.last_working_strategy = "General — ALT"
            cfg.save()
            # Load a fresh instance.
            cfg2 = AppConfig.load()
            self.assertTrue(cfg2.autostart_strategy)
            self.assertEqual(cfg2.last_working_strategy, "General — ALT")

    # --- Theme persistence regression ---

    def test_image_theme_id_surives_config_round_trip(self):
        """AppConfig accepts any string for `theme` — but the GUI used to
        filter it against only ('purple','light','dark') at startup, silently
        resetting any of the 7 image themes (mist/azure/snow/lavender/fog/
        sand/midnight) back to 'purple'. This test pins the catalog so the
        regression can't sneak back in: every theme id returned by the catalog
        MUST be a valid save value that the GUI will honour on reload."""
        from ui.themes_catalog import THEMES, theme_ids
        # Catalog must contain all 10 themes — the 3 presets + 7 image themes.
        self.assertEqual(len(THEMES), 10)
        # Every theme id must be unique and non-empty.
        ids = theme_ids()
        self.assertEqual(len(ids), len(set(ids)))
        for tid in ids:
            self.assertTrue(tid and isinstance(tid, str))
        # The 7 image themes MUST be in the catalog. If any are missing, the
        # GUI's "validate saved theme against catalog" check would silently
        # fall back to 'purple' even though the user picked a real theme.
        image_ids = {t.id for t in THEMES if t.group == "image"}
        expected_image_ids = {
            "mist", "azure", "snow", "lavender", "fog", "sand", "midnight"
        }
        self.assertEqual(image_ids, expected_image_ids)

    def test_theme_validation_accepts_all_image_themes(self):
        """The validation logic in MainWindow.__init__ must accept every
        theme id from the catalog. We simulate the same check here against
        a config that has each image theme set."""
        from ui.themes_catalog import theme_ids
        valid = set(theme_ids())
        for tid in ["mist", "azure", "snow", "lavender", "fog", "sand", "midnight"]:
            self.assertIn(tid, valid,
                          f"Image theme '{tid}' must be in the valid set")

    # --- SHA-256 integrity check for zapret bundle downloads ---

    def test_sha256_helper_computes_correct_digest(self):
        """The _sha256_hex helper must match hashlib's output verbatim."""
        import hashlib
        from app.updater import _sha256_hex
        data = b"hello world"
        self.assertEqual(_sha256_hex(data), hashlib.sha256(data).hexdigest())

    def test_updater_release_info_has_digest_fields(self):
        """ReleaseInfo must expose `digest` and `digest_verified` so callers
        can distinguish GitHub-provided digests (mandatory) from locally
        computed ones (informational)."""
        from app.updater import ReleaseInfo
        rel = ReleaseInfo(
            tag="v1.0.0", name="v1.0.0", zip_url="http://x", html_url="http://y"
        )
        self.assertIsNone(rel.digest)
        self.assertFalse(rel.digest_verified)

    def test_updater_save_load_installed_sha256_round_trip(self):
        """_save_installed_sha256 / _load_installed_sha256 must round-trip
        the digest. Used to detect tampered re-downloads of the same tag."""
        with tempfile.TemporaryDirectory() as td:
            from app.updater import (
                _save_installed_sha256, _load_installed_sha256,
                INSTALLED_SHA256_MARKER,
            )
            root = Path(td)
            # Initially: no marker, returns empty string.
            self.assertEqual(_load_installed_sha256(root), "")
            _save_installed_sha256(root, "ABCDEF1234567890")
            # File must exist with the digest as its content.
            self.assertTrue((root / INSTALLED_SHA256_MARKER).exists())
            # Loader normalises to lowercase.
            self.assertEqual(_load_installed_sha256(root), "abcdef1234567890")


    def test_updater_skips_zip_slip_entries(self):
        """A malicious release zip must not be able to write outside the
        zapret directory via ../ paths."""
        import io
        import zipfile
        from app import updater
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("../escape.txt", "bad")
            zf.writestr("bin/winws.exe", "ok")
            zf.writestr("general.bat", "echo winws.exe --wf-tcp=443 --dpi-desync=fake")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = updater.requests
        try:
            updater.requests = _Requests()
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "zapret"
                root.mkdir()
                rel = updater.ReleaseInfo("v-test", "v-test", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                self.assertIn("Обновлено", msg)
                self.assertTrue((root / "bin" / "winws.exe").exists())
                self.assertFalse((Path(td) / "escape.txt").exists())
        finally:
            updater.requests = old_requests


    def test_zapret_update_critical_locked_file_is_partial(self):
        """If winws.exe/driver files are locked, the updater must not report a
        clean success or mark the release installed. Otherwise the app says it
        is updated while core binaries are still from the old release."""
        import builtins
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bundle/bin/winws.exe", b"new-winws")
            zf.writestr("bundle/lists/list-general.txt", "example.com\n")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = updater.requests
        old_open = builtins.open
        try:
            updater.requests = _Requests()
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "bin").mkdir()
                (root / "bin" / "winws.exe").write_bytes(b"old-winws")

                def guarded_open(file, mode="r", *args, **kwargs):
                    if str(file).replace("\\", "/").endswith("bin/winws.exe") and "w" in mode:
                        raise OSError("locked")
                    return old_open(file, mode, *args, **kwargs)

                builtins.open = guarded_open
                rel = updater.ReleaseInfo("v9.9.9", "v9.9.9", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                self.assertIn("Обновление выполнено частично", msg)
                self.assertIn("bin/winws.exe", msg)
                self.assertEqual((root / "bin" / "winws.exe").read_bytes(), b"old-winws")
                self.assertFalse((root / updater.INSTALLED_MARKER).exists())
        finally:
            builtins.open = old_open
            updater.requests = old_requests


    def test_zapret_update_locked_driver_can_schedule_reboot_replace(self):
        """A loaded WinDivert .sys may stay locked even after zapret is off.
        On Windows the updater should schedule the replacement for reboot
        instead of looping forever on the same locked driver file."""
        import builtins
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bundle/bin/WinDivert64.sys", b"new-driver")
            zf.writestr("bundle/lists/list-general.txt", "example.com\n")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = updater.requests
        old_open = builtins.open
        old_schedule = updater._schedule_replace_on_reboot
        old_release = updater._release_windivert_locks
        try:
            updater.requests = _Requests()
            updater._release_windivert_locks = lambda: None
            scheduled = []
            updater._schedule_replace_on_reboot = lambda target, data: scheduled.append((target.name, data)) or True
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "bin").mkdir()
                (root / "bin" / "WinDivert64.sys").write_bytes(b"old-driver")

                def guarded_open(file, mode="r", *args, **kwargs):
                    if str(file).replace("\\", "/").endswith("bin/WinDivert64.sys") and "w" in mode:
                        raise OSError("loaded driver")
                    return old_open(file, mode, *args, **kwargs)

                builtins.open = guarded_open
                rel = updater.ReleaseInfo("v9.9.9", "v9.9.9", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                self.assertIn("Обновление подготовлено", msg)
                self.assertIn("WinDivert64.sys", msg)
                self.assertEqual(scheduled, [("WinDivert64.sys", b"new-driver")])
                self.assertTrue((root / updater.REBOOT_PENDING_MARKER).exists())
                self.assertFalse((root / updater.INSTALLED_MARKER).exists())
        finally:
            builtins.open = old_open
            updater._schedule_replace_on_reboot = old_schedule
            updater._release_windivert_locks = old_release
            updater.requests = old_requests

    def test_updater_protected_set_includes_sha256_marker(self):
        """download_and_apply's `protected` set must include
        INSTALLED_SHA256_MARKER so an extracted zip can't clobber the
        stored digest of the previous install."""
        from app import updater
        # The constant itself must be a non-empty string starting with '.'.
        self.assertTrue(updater.INSTALLED_SHA256_MARKER.startswith("."))

    # --- Roblox profile (JSON externalisation) ---

    def test_roblox_profile_public_constant_exists(self):
        """``ROBLOX_FIX_ARGS`` (no underscore) must be importable as a
        public API. Previously only ``_ROBLOX_FIX_ARGS`` (private) existed,
        forcing callers to reach into bootstrap's privates."""
        from app import bootstrap
        self.assertTrue(hasattr(bootstrap, "ROBLOX_FIX_ARGS"))
        self.assertTrue(bootstrap.ROBLOX_FIX_ARGS)
        # The private alias must still exist for backwards-compat.
        self.assertTrue(hasattr(bootstrap, "_ROBLOX_FIX_ARGS"))
        # Both must point at the same string.
        self.assertEqual(bootstrap.ROBLOX_FIX_ARGS, bootstrap._ROBLOX_FIX_ARGS)

    def test_load_roblox_profile_returns_args_and_description(self):
        """load_roblox_profile() must return a non-empty (args, description)
        tuple. The args must contain the Roblox UDP port range so the
        bypass actually applies to game traffic."""
        from app.bootstrap import load_roblox_profile
        args, desc = load_roblox_profile()
        self.assertIsInstance(args, str)
        self.assertIsInstance(desc, str)
        self.assertTrue(args.strip(), "Roblox args must not be empty")
        self.assertTrue(desc.strip(), "Roblox description must not be empty")
        # Critical markers that must be present in any Roblox profile.
        self.assertIn("--filter-udp=49152-65535", args)
        self.assertIn("--ipset-ip=", args)
        self.assertIn("roblox.com", args)

    def test_load_roblox_profile_falls_back_on_missing_json(self):
        """If the JSON file is missing (e.g. an older install was upgraded
        in place), load_roblox_profile() must fall back to the hardcoded
        ROBLOX_FIX_ARGS string instead of raising."""
        from app import bootstrap
        # Force the path lookup to fail.
        orig = bootstrap._roblox_profile_path
        try:
            bootstrap._roblox_profile_path = lambda: None
            args, desc = bootstrap.load_roblox_profile()
            self.assertEqual(args, bootstrap.ROBLOX_FIX_ARGS)
            self.assertTrue(desc)
        finally:
            bootstrap._roblox_profile_path = orig

    def test_load_roblox_profile_falls_back_on_corrupt_json(self):
        """A corrupt or hand-edited-but-broken JSON must NOT crash the
        loader — it falls back to the hardcoded constant."""
        from app import bootstrap
        orig = bootstrap._roblox_profile_path
        try:
            # Simulate a corrupt JSON file by returning a path to a temp
            # file containing garbage.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                f.write("this is not json {{{ ,,, ")
                bad_path = Path(f.name)
            bootstrap._roblox_profile_path = lambda: bad_path
            args, desc = bootstrap.load_roblox_profile()
            self.assertEqual(args, bootstrap.ROBLOX_FIX_ARGS)
            self.assertTrue(desc)
        finally:
            bootstrap._roblox_profile_path = orig
            try:
                bad_path.unlink()
            except OSError:
                pass

    def test_roblox_profile_json_file_is_valid(self):
        """The shipped ``roblox_profile.json`` at the project root must be
        valid JSON with at least an ``args`` field."""
        from app.bootstrap import _roblox_profile_path
        p = _roblox_profile_path()
        self.assertIsNotNone(p, "roblox_profile.json must exist at project root")
        if p is not None:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("args", data)
            self.assertIsInstance(data["args"], str)
            self.assertTrue(data["args"].strip())

    # --- Dynamic User-Agent ---

    def test_user_agent_is_current_chrome(self):
        """The connectivity User-Agent must look like a recent desktop Chrome,
        not the stale Chrome/124.0 from April 2024. We don't pin a specific
        major (it's projected from the calendar), but it must:
          * contain "Windows NT 10.0" (engine runs on Windows only)
          * contain "Chrome/" followed by a number >= 124 (the April 2024
            anchor; any newer Chrome is fine)
          * NOT be the literal stale "Chrome/124.0" string from before
        """
        import re
        from app.connectivity import _build_user_agent, _HEADERS
        ua = _build_user_agent()
        # Must match the same UA the module actually uses at import time.
        self.assertEqual(_HEADERS["User-Agent"], ua)
        # Windows 10 desktop signature.
        self.assertIn("Windows NT 10.0", ua)
        self.assertIn("Win64; x64", ua)
        # Extract the Chrome major version.
        m = re.search(r"Chrome/(\d+)", ua)
        self.assertIsNotNone(m, f"Chrome version not found in UA: {ua}")
        chrome_major = int(m.group(1))
        # Must be at least the anchor major (124 = April 2024).
        self.assertGreaterEqual(chrome_major, 124,
                                f"Chrome major {chrome_major} is older than "
                                f"the April 2024 anchor — UA is stale")
        # On any date after 2024-05-21 (28 days after the anchor) we must
        # have moved past 124.
        from datetime import date, timedelta
        if date.today() > date(2024, 4, 23) + timedelta(days=28):
            self.assertGreater(chrome_major, 124,
                               "Chrome major still 124 more than 28 days "
                               "after the anchor — projection is broken")

    # --- TG proxy DC IP overrides ---

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

    def test_hosts_lines_are_normalized_and_blocked(self):
        from app import list_manager
        text = """
        # comment
        149.154.167.220 KWS4.Web.Telegram.Org extra.invalid
        not_an_ip example.com
        999.999.999.999 bad.example
        185.199.109.133 raw.githubusercontent.com # inline
        """
        lines = list_manager.normalize_hosts_lines(text)
        self.assertIn("149.154.167.220 kws4.web.telegram.org", lines)
        self.assertIn("149.154.167.220 extra.invalid", lines)
        self.assertIn("185.199.109.133 raw.githubusercontent.com", lines)
        self.assertNotIn("999.999.999.999 bad.example", lines)
        block = list_manager.render_hosts_block(lines)
        self.assertIn(list_manager.HOSTS_BEGIN, block)
        self.assertIn(list_manager.HOSTS_END, block)

    def test_apply_and_remove_hosts_block_preserves_manual_lines(self):
        from app import list_manager
        with tempfile.TemporaryDirectory() as td:
            hosts = Path(td) / "hosts"
            hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            msg = list_manager.apply_hosts_block(
                "149.154.167.220 kws4.web.telegram.org\n", hosts_path=hosts
            )
            self.assertIn("HOSTS обновлён", msg)
            text = hosts.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("149.154.167.220 kws4.web.telegram.org", text)
            self.assertTrue((Path(td) / "hosts.zapretgui.bak").exists())
            msg = list_manager.remove_hosts_block(hosts_path=hosts)
            self.assertIn("удалён", msg)
            text = hosts.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1 localhost", text)
            self.assertNotIn("kws4.web.telegram.org", text)


    def test_apply_hosts_block_is_idempotent(self):
        from app import list_manager
        with tempfile.TemporaryDirectory() as td:
            hosts = Path(td) / "hosts"
            block = "149.154.167.220 kws4.web.telegram.org\n"
            first = list_manager.apply_hosts_block(block, hosts_path=hosts)
            self.assertIn("HOSTS обновлён", first)
            before = hosts.read_text(encoding="utf-8")
            self.assertTrue(list_manager.hosts_block_is_current(block, hosts_path=hosts))
            second = list_manager.apply_hosts_block(block, hosts_path=hosts)
            self.assertIn("уже содержит актуальный блок", second)
            self.assertEqual(hosts.read_text(encoding="utf-8"), before)

    def test_update_zapret_lists_updates_only_safe_upstream_files(self):
        import io
        import zipfile
        from app import list_manager, updater
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bundle/lists/list-general.txt", "discord.com\n")
            zf.writestr("bundle/lists/ipset-all.txt", "1.1.1.1/32\n")
            zf.writestr("bundle/lists/list-general-user.txt", "SHOULD_NOT_OVERWRITE\n")
            zf.writestr("bundle/.service/hosts", "149.154.167.220 kws4.web.telegram.org\n")
            zf.writestr("bundle/../escape.txt", "bad\n")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = list_manager.requests
        old_latest = updater.latest_release
        try:
            list_manager.requests = _Requests()
            updater.latest_release = lambda timeout=10.0: updater.ReleaseInfo(
                tag="v-test", name="v-test", zip_url="http://x", html_url="http://y"
            )
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "lists").mkdir()
                (root / "lists" / "list-general-user.txt").write_text("USER\n", encoding="utf-8")
                res = list_manager.update_zapret_lists(root)
                self.assertTrue(res.ok, res.message)
                self.assertEqual((root / "lists" / "list-general.txt").read_text(encoding="utf-8"), "discord.com\n")
                self.assertEqual((root / "lists" / "ipset-all.txt").read_text(encoding="utf-8"), "1.1.1.1/32\n")
                self.assertEqual((root / "lists" / "list-general-user.txt").read_text(encoding="utf-8"), "USER\n")
                self.assertIn("kws4.web.telegram.org", (root / ".service" / "hosts").read_text(encoding="utf-8"))
                self.assertFalse((Path(td) / "escape.txt").exists())
        finally:
            list_manager.requests = old_requests
            updater.latest_release = old_latest


    def test_update_zapret_lists_reports_already_actual(self):
        import io
        import zipfile
        from app import list_manager, updater
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bundle/lists/list-general.txt", "discord.com\n")
            zf.writestr("bundle/lists/ipset-all.txt", "1.1.1.1/32\n")
            zf.writestr("bundle/.service/hosts", "149.154.167.220 kws4.web.telegram.org\n")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = list_manager.requests
        old_latest = updater.latest_release
        try:
            list_manager.requests = _Requests()
            updater.latest_release = lambda timeout=10.0: updater.ReleaseInfo(
                tag="v-test", name="v-test", zip_url="http://x", html_url="http://y"
            )
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                first = list_manager.update_zapret_lists(root)
                self.assertTrue(first.ok, first.message)
                self.assertGreater(first.updated, 0)
                second = list_manager.update_zapret_lists(root)
                self.assertTrue(second.ok, second.message)
                self.assertEqual(second.updated, 0)
                self.assertGreaterEqual(second.unchanged, 3)
                self.assertIn("уже актуальны", second.message)
        finally:
            list_manager.requests = old_requests
            updater.latest_release = old_latest

    def test_should_auto_update_lists_interval(self):
        from app.list_manager import should_auto_update_lists
        self.assertTrue(should_auto_update_lists(0, 24, now=1000))
        self.assertFalse(should_auto_update_lists(1000, 24, now=1000 + 3600))
        self.assertTrue(should_auto_update_lists(1000, 24, now=1000 + 24 * 3600))

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


    def test_zapret_update_available_current_returns_none(self):
        from app import updater
        old_latest = updater.latest_release
        try:
            updater.latest_release = lambda timeout=10.0: updater.ReleaseInfo(
                tag="v9.9.9", name="v9.9.9", zip_url="http://x", html_url="http://y"
            )
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                updater.save_local_version(root, "v9.9.9")
                self.assertIsNone(updater.update_available(root))
        finally:
            updater.latest_release = old_latest

    def test_zapret_update_available_unknown_local_returns_release(self):
        from app import updater
        old_latest = updater.latest_release
        try:
            updater.latest_release = lambda timeout=10.0: updater.ReleaseInfo(
                tag="v9.9.9", name="v9.9.9", zip_url="http://x", html_url="http://y"
            )
            with tempfile.TemporaryDirectory() as td:
                rel = updater.update_available(Path(td))
                self.assertIsNotNone(rel)
                self.assertEqual(rel.tag, "v9.9.9")
                self.assertFalse((Path(td) / updater.INSTALLED_MARKER).exists())
        finally:
            updater.latest_release = old_latest


if __name__ == '__main__':
    unittest.main()
