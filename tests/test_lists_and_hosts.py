"""Domain lists, SoundCloud preset, hosts snippets and list updates."""
from pathlib import Path
import tempfile
import unittest
from app.exclusions import apply_lists, resolve_domains


class ListsAndHostsTests(unittest.TestCase):

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
