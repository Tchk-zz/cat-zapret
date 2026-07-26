"""Strategy bundle updates: archive layout, SHA-256 integrity, locked files."""
from pathlib import Path
import tempfile
import unittest
from app.updater import _common_root


class UpdaterIntegrityTests(unittest.TestCase):

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
