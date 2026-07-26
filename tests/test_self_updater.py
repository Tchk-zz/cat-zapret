"""Offline tests for the in-app update flow (app/self_updater.py).

This is the most dangerous code in the project: it downloads an executable and
starts it with admin rights, and it already broke twice in production (Setup
killed its own process; an unverifiable installer was nearly executed). Until
now nothing in the suite touched it.

The tests never reach the network and never start a real installer: the
``requests`` module is replaced with a fake, ``subprocess.Popen`` is patched and
the temp folder is redirected into a throwaway directory.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
from app import self_updater as su

_DIGEST_PREFIX = "sha256:"


class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload=None, chunks=(), headers=None):
        self._payload = payload
        self._chunks = list(chunks)
        self.headers = dict(headers or {})
        self.closed = False

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=65536):
        for chunk in self._chunks:
            yield chunk

    def close(self):
        self.closed = True


class _FakeRequests:
    """Stand-in for the requests module: returns a canned response or raises."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.response


def _api_payload(tag="v9.9.9", asset_name=None, digest=_DIGEST_PREFIX + "ab" * 32):
    """Build a GitHub "latest release" payload with an extra unrelated asset."""
    name = asset_name or su.INSTALLER_ASSET
    asset = {
        "name": name,
        "browser_download_url": "https://example.invalid/" + name,
        "size": 55 * 1024 * 1024,
    }
    if digest:
        asset["digest"] = digest
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": "Source code.zip",
                "browser_download_url": "https://example.invalid/src.zip",
                "size": 123,
            },
            asset,
        ],
    }


class VersionHelperTests(unittest.TestCase):

    def test_short_tag_equals_padded_version(self):
        # "v1.8" and "1.8.0" are the same release; without padding the app
        # offered a bogus update.
        self.assertEqual(su._norm("v1.8"), su._norm("1.8.0"))

    def test_ten_sorts_above_nine(self):
        self.assertGreater(su._norm("1.8.10"), su._norm("1.8.9"))

    def test_garbage_component_does_not_crash(self):
        self.assertEqual(su._norm("1.8.beta"), (1, 8, 0))

    def test_local_version_matches_version_file(self):
        root = Path(__file__).resolve().parent.parent
        expected = (root / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(su.local_version(), expected)

    def test_package_version_is_not_hardcoded(self):
        # app/__init__.py used to hardcode "1.0.0" while the app shipped 1.8.x.
        # It must always agree with the VERSION file the updater compares.
        self.assertEqual(app.__version__, su.local_version())


class DigestParsingTests(unittest.TestCase):

    def test_uppercase_digest_is_lowercased(self):
        asset = {"digest": _DIGEST_PREFIX + "AB" * 32}
        self.assertEqual(su._parse_digest(asset), "ab" * 32)

    def test_missing_digest_returns_empty(self):
        self.assertEqual(su._parse_digest({}), "")

    def test_foreign_algorithm_is_rejected(self):
        self.assertEqual(su._parse_digest({"digest": "md5:" + "ab" * 16}), "")


class LatestReleaseTests(unittest.TestCase):

    def _latest(self, requests_stub):
        with mock.patch.object(su, "_requests", requests_stub):
            return su.latest_release()

    def test_picks_installer_asset_and_digest(self):
        stub = _FakeRequests(_FakeResponse(payload=_api_payload()))
        rel = self._latest(stub)
        self.assertIsNotNone(rel)
        self.assertEqual(rel.tag, "v9.9.9")
        self.assertEqual(rel.version, "9.9.9")
        self.assertTrue(rel.download_url.endswith(su.INSTALLER_ASSET))
        self.assertEqual(rel.sha256, "ab" * 32)
        self.assertEqual(stub.urls, [su.RELEASES_API])

    def test_release_without_installer_asset_is_ignored(self):
        payload = _api_payload(asset_name="ZapretGUI-portable.zip")
        self.assertIsNone(self._latest(_FakeRequests(_FakeResponse(payload=payload))))

    def test_missing_tag_is_ignored(self):
        payload = _api_payload()
        payload["tag_name"] = ""
        self.assertIsNone(self._latest(_FakeRequests(_FakeResponse(payload=payload))))

    def test_network_failure_returns_none(self):
        self.assertIsNone(self._latest(_FakeRequests(error=OSError("no network"))))


class CheckUpdateTests(unittest.TestCase):

    def _release(self, tag):
        return su.AppRelease(
            tag=tag,
            version=tag.lstrip("v"),
            download_url="https://example.invalid/setup.exe",
            size=1,
            sha256="ab" * 32,
        )

    def _check(self, tag_or_none, local):
        rel = None if tag_or_none is None else self._release(tag_or_none)
        with mock.patch.object(su, "latest_release", return_value=rel), \
                mock.patch.object(su, "local_version", return_value=local):
            return su.check_update()

    def test_newer_release_offers_update(self):
        status, rel = self._check("v1.9.0", "1.8.4")
        self.assertEqual(status, "update")
        self.assertEqual(rel.version, "1.9.0")

    def test_same_version_is_uptodate(self):
        self.assertEqual(self._check("v1.8.4", "1.8.4"), ("uptodate", None))

    def test_older_release_is_uptodate(self):
        self.assertEqual(self._check("v1.8.0", "1.8.4"), ("uptodate", None))

    def test_failed_lookup_reports_error(self):
        self.assertEqual(self._check(None, "1.8.4"), ("error", None))

    def test_unknown_local_version_reports_error_not_endless_update(self):
        # Regression: a missing VERSION file next to the exe used to yield
        # ("update", rel) forever, so the app kept re-offering the same release.
        self.assertEqual(self._check("v1.8.4", ""), ("error", None))


class PurgeStaleInstallersTests(unittest.TestCase):

    def test_keeps_only_the_current_installer(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            keep = tmp / (su._TMP_PREFIX + "keep.exe")
            stale = tmp / (su._TMP_PREFIX + "old.exe")
            other = tmp / "unrelated.exe"
            for path in (keep, stale, other):
                path.write_bytes(b"x")
            with mock.patch.object(su.tempfile, "gettempdir", return_value=td):
                su._purge_stale_installers(keep=str(keep))
            self.assertTrue(keep.exists())
            self.assertFalse(stale.exists())
            self.assertTrue(other.exists())


class DownloadAndLaunchTests(unittest.TestCase):

    CHUNKS = (b"setup-part-1", b"setup-part-2")

    def _real_digest(self):
        return hashlib.sha256(b"".join(self.CHUNKS)).hexdigest()

    def _run(self, sha256, should_cancel=None, popen_error=None, download_error=None):
        """Run download_and_launch against a fake CDN inside a temp folder.

        Returns (result, leftover file count, Popen call count, statuses).
        """
        total = sum(len(c) for c in self.CHUNKS)
        rel = su.AppRelease(
            tag="v9.9.9",
            version="9.9.9",
            download_url="https://example.invalid/" + su.INSTALLER_ASSET,
            size=total,
            sha256=sha256,
        )
        response = _FakeResponse(
            chunks=self.CHUNKS,
            headers={"Content-Length": str(total)},
        )
        stub = _FakeRequests(response, error=download_error)
        statuses = []
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(su.tempfile, "gettempdir", return_value=td), \
                    mock.patch.object(su, "_requests", stub), \
                    mock.patch.object(su.subprocess, "Popen") as popen:
                if popen_error is not None:
                    popen.side_effect = popen_error
                result = su.download_and_launch(
                    rel,
                    on_status=statuses.append,
                    should_cancel=should_cancel,
                )
                leftovers = len(list(Path(td).glob(su._TMP_PREFIX + "*.exe")))
                launches = popen.call_count
        return result, leftovers, launches, statuses

    def test_verified_installer_is_launched_and_kept(self):
        result, leftovers, launches, statuses = self._run(self._real_digest())
        self.assertEqual(result, "ok")
        self.assertEqual(launches, 1)
        # The launched file must survive: Windows locks it while Setup runs.
        self.assertEqual(leftovers, 1)
        self.assertTrue(any("SHA-256" in s for s in statuses))

    def test_checksum_mismatch_refuses_and_deletes(self):
        result, leftovers, launches, _ = self._run("00" * 32)
        self.assertTrue(result.startswith("Ошибка"))
        self.assertEqual(launches, 0)
        self.assertEqual(leftovers, 0)

    def test_missing_published_checksum_refuses(self):
        # An installer we cannot verify must never be started with admin rights.
        result, leftovers, launches, _ = self._run("")
        self.assertTrue(result.startswith("Ошибка"))
        self.assertIn("SHA-256", result)
        self.assertEqual(launches, 0)
        self.assertEqual(leftovers, 0)

    def test_cancel_aborts_and_deletes_partial_file(self):
        result, leftovers, launches, _ = self._run(
            self._real_digest(), should_cancel=lambda: True
        )
        self.assertEqual(result, "cancelled")
        self.assertEqual(launches, 0)
        self.assertEqual(leftovers, 0)

    def test_download_failure_is_reported(self):
        result, _, launches, _ = self._run(
            self._real_digest(), download_error=OSError("connection reset")
        )
        self.assertTrue(result.startswith("Ошибка загрузки"))
        self.assertEqual(launches, 0)

    def test_launch_failure_deletes_installer(self):
        result, leftovers, _, _ = self._run(
            self._real_digest(), popen_error=OSError("access denied")
        )
        self.assertTrue(result.startswith("Ошибка запуска"))
        self.assertEqual(leftovers, 0)

    def test_progress_reaches_one_hundred(self):
        total = sum(len(c) for c in self.CHUNKS)
        rel = su.AppRelease(
            tag="v9.9.9",
            version="9.9.9",
            download_url="https://example.invalid/" + su.INSTALLER_ASSET,
            size=total,
            sha256=self._real_digest(),
        )
        stub = _FakeRequests(
            _FakeResponse(chunks=self.CHUNKS, headers={"Content-Length": str(total)})
        )
        seen = []
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(su.tempfile, "gettempdir", return_value=td), \
                    mock.patch.object(su, "_requests", stub), \
                    mock.patch.object(su.subprocess, "Popen"):
                su.download_and_launch(rel, on_progress=seen.append)
        self.assertTrue(seen)
        self.assertEqual(seen[-1], 100)
        self.assertTrue(all(0 <= p <= 100 for p in seen))


if __name__ == "__main__":
    unittest.main()
