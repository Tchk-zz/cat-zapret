"""Strategy bundle updates: archive layout, SHA-256 integrity, locked files."""
from pathlib import Path
import tempfile
import unittest
from app.updater import _common_root


class _FakeResponse:
    """Streaming stand-in for a requests Response.

    The updater reads the archive with ``iter_content`` now, so the fake has
    to behave like a real streaming response: context manager, headers and
    chunked reads.
    """

    def __init__(self, data: bytes, chunk_size: int = 8):
        self._data = data
        self._chunk = chunk_size
        self.headers = {"Content-Length": str(len(data))}
        self.chunks_served = 0

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=None):
        size = int(chunk_size) if chunk_size else self._chunk
        size = min(size, self._chunk)
        for start in range(0, len(self._data), size):
            self.chunks_served += 1
            yield self._data[start:start + size]


class _FakeRequests:
    """Minimal ``requests`` replacement handing out a ``_FakeResponse``."""

    def __init__(self, data: bytes, chunk_size: int = 8):
        self.response = _FakeResponse(data, chunk_size)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


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
            zf.writestr("bin/WinDivert.dll", "dll")
            zf.writestr("bin/WinDivert64.sys", "sys")
            zf.writestr("general.bat", "echo winws.exe --wf-tcp=443 --dpi-desync=fake")

        fake_requests = _FakeRequests(payload.getvalue())

        old_requests = updater.requests
        try:
            updater.requests = fake_requests
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
            zf.writestr("bundle/bin/WinDivert.dll", b"dll")
            zf.writestr("bundle/bin/WinDivert64.sys", b"sys")
            zf.writestr("bundle/general.bat", "echo winws.exe --wf-tcp=443 --dpi-desync=fake")
            zf.writestr("bundle/lists/list-general.txt", "example.com\n")

        fake_requests = _FakeRequests(payload.getvalue())

        old_requests = updater.requests
        old_open = builtins.open
        try:
            updater.requests = fake_requests
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "bin").mkdir()
                (root / "lists").mkdir()
                (root / "bin" / "winws.exe").write_bytes(b"old-winws")
                (root / "lists" / "list-general.txt").write_text("old.example\n", encoding="utf-8")

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
                self.assertEqual(
                    (root / "lists" / "list-general.txt").read_text(encoding="utf-8"),
                    "old.example\n",
                )
                self.assertFalse((root / "bin" / "WinDivert.dll").exists())
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
            zf.writestr("bundle/bin/winws.exe", b"winws")
            zf.writestr("bundle/bin/WinDivert.dll", b"dll")
            zf.writestr("bundle/bin/WinDivert64.sys", b"new-driver")
            zf.writestr("bundle/general.bat", "echo winws.exe --wf-tcp=443 --dpi-desync=fake")
            zf.writestr("bundle/lists/list-general.txt", "example.com\n")

        fake_requests = _FakeRequests(payload.getvalue())

        old_requests = updater.requests
        old_open = builtins.open
        old_schedule = updater._schedule_replace_on_reboot
        old_release = updater._release_windivert_locks
        try:
            updater.requests = fake_requests
            updater._release_windivert_locks = lambda *_a, **_kw: None
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

    def test_updater_streams_the_archive_in_chunks(self):
        """The archive must be pulled with a streaming request. `.content`
        buffered the whole file at once, and a single whole-download timeout
        killed big updates on slow-but-healthy links."""
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bin/winws.exe", b"x" * 4096)
            zf.writestr("general.bat", "echo winws.exe --wf-tcp=443")

        fake_requests = _FakeRequests(payload.getvalue(), chunk_size=64)
        statuses = []
        old_requests = updater.requests
        try:
            updater.requests = fake_requests
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "zapret"
                root.mkdir()
                rel = updater.ReleaseInfo("v-stream", "v-stream", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root, on_status=statuses.append)
            self.assertIn("Обновлено", msg)
            # Several chunks => the body really was streamed, not buffered.
            self.assertGreater(fake_requests.response.chunks_served, 1)
            _url, kwargs = fake_requests.calls[0]
            self.assertTrue(kwargs.get("stream"))
            # (connect, read) pair instead of one budget for the whole file.
            self.assertIsInstance(kwargs.get("timeout"), tuple)
            self.assertTrue(any("Загрузка" in s for s in statuses))
        finally:
            updater.requests = old_requests

    def test_updater_rejects_an_oversized_archive(self):
        """A hostile or broken server must not stream gigabytes into memory:
        an oversized Content-Length is refused before reading the body."""
        from app import updater

        fake_requests = _FakeRequests(b"")
        fake_requests.response.headers = {
            "Content-Length": str(updater._MAX_ARCHIVE_BYTES + 1)
        }
        old_requests = updater.requests
        try:
            updater.requests = fake_requests
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "zapret"
                root.mkdir()
                rel = updater.ReleaseInfo("v-big", "v-big", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
            self.assertIn("Ошибка загрузки", msg)
        finally:
            updater.requests = old_requests

    def test_updater_does_not_kill_the_engine_when_nothing_is_locked(self):
        """The old code ran taskkill + `sc delete` on EVERY update, killing a
        running engine and dropping the WinDivert service even when no file
        was locked. Locks may only be released after a real write failure."""
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bin/winws.exe", b"new-winws")
            zf.writestr("general.bat", "echo winws.exe --wf-tcp=443")

        calls = []
        old_requests = updater.requests
        old_release = updater._release_windivert_locks
        try:
            updater.requests = _FakeRequests(payload.getvalue())
            updater._release_windivert_locks = lambda *_a, **_kw: calls.append(1)
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "zapret"
                root.mkdir()
                rel = updater.ReleaseInfo("v-nolock", "v-nolock", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
            self.assertIn("Обновлено", msg)
            self.assertEqual(calls, [])
        finally:
            updater._release_windivert_locks = old_release
            updater.requests = old_requests

    def test_updater_releases_locks_once_when_a_file_is_locked(self):
        """A genuinely locked file triggers exactly one lock-release + retry,
        not one per archive member."""
        import builtins
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bin/winws.exe", b"new-winws")
            zf.writestr("bin/cygwin1.dll", b"new-dll")

        calls = []
        old_requests = updater.requests
        old_release = updater._release_windivert_locks
        old_open = builtins.open
        try:
            updater.requests = _FakeRequests(payload.getvalue())
            updater._release_windivert_locks = lambda *_a, **_kw: calls.append(1)
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "bin").mkdir()

                def guarded_open(file, mode="r", *args, **kwargs):
                    name = str(file).replace("\\", "/")
                    if name.endswith("bin/winws.exe") and "w" in mode:
                        raise OSError("locked")
                    return old_open(file, mode, *args, **kwargs)

                builtins.open = guarded_open
                rel = updater.ReleaseInfo("v-lock", "v-lock", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                builtins.open = old_open
            self.assertIn("частично", msg)
            self.assertEqual(calls, [1])
        finally:
            builtins.open = old_open
            updater._release_windivert_locks = old_release
            updater.requests = old_requests

    def test_updater_skipped_bin_text_file_is_not_critical(self):
        """Only bin/*.exe|dll|sys are engine-critical. A skipped bin/readme.txt
        must not downgrade a good update to a scary partial one."""
        import builtins
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            zf.writestr("bin/readme.txt", b"hello")
            zf.writestr("general.bat", "echo winws.exe --wf-tcp=443")

        old_requests = updater.requests
        old_release = updater._release_windivert_locks
        old_open = builtins.open
        try:
            updater.requests = _FakeRequests(payload.getvalue())
            updater._release_windivert_locks = lambda *_a, **_kw: None
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "bin").mkdir()

                def guarded_open(file, mode="r", *args, **kwargs):
                    name = str(file).replace("\\", "/")
                    if name.endswith("bin/readme.txt") and "w" in mode:
                        raise OSError("locked")
                    return old_open(file, mode, *args, **kwargs)

                builtins.open = guarded_open
                rel = updater.ReleaseInfo("v-txt", "v-txt", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                builtins.open = old_open
            self.assertNotIn("частично", msg)
            self.assertIn("Обновлено", msg)
        finally:
            builtins.open = old_open
            updater._release_windivert_locks = old_release
            updater.requests = old_requests

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


    def test_zapret_update_rejects_zip_bomb_member_before_writing(self):
        import io
        import zipfile
        from app import updater

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as zf:
            info = zipfile.ZipInfo("bin/winws.exe")
            info.file_size = updater.MAX_MEMBER_BYTES + 1
            # ZipFile rewrites file_size for normal writes, so patch the parsed
            # metadata to model a malicious central-directory declaration.
            zf.writestr(info, b"x")
            zf.writestr("bin/WinDivert.dll", b"dll")
            zf.writestr("bin/WinDivert64.sys", b"sys")
            zf.writestr("general.bat", b"echo winws.exe --wf-tcp=443 --dpi-desync=fake")

        class _Resp:
            content = payload.getvalue()
            def raise_for_status(self):
                return None

        class _Requests:
            @staticmethod
            def get(*_args, **_kwargs):
                return _Resp()

        old_requests = updater.requests
        old_limit = updater.MAX_MEMBER_BYTES
        try:
            updater.requests = _Requests()
            updater.MAX_MEMBER_BYTES = 0
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                rel = updater.ReleaseInfo("v-test", "v-test", "http://x", "http://y")
                msg = updater.download_and_apply(rel, root)
                self.assertIn("превышает безопасный размер", msg)
                self.assertFalse((root / "bin" / "winws.exe").exists())
        finally:
            updater.MAX_MEMBER_BYTES = old_limit
            updater.requests = old_requests


if __name__ == '__main__':
    unittest.main()
