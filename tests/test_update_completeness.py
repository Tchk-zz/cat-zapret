"""Regression coverage for complete Flowseal bundle/list update semantics."""
from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path


class _Response:
    def __init__(self, data: bytes):
        self._data = data
        self.content = data
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=256 * 1024):
        for start in range(0, len(self._data), chunk_size):
            yield self._data[start:start + chunk_size]


class _Requests:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.payloads[url])


def _zip_bytes(files: dict[str, bytes | str]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return payload.getvalue()


def _asset(extra=None) -> bytes:
    files = {
        "bin/winws.exe": b"winws-new",
        "bin/WinDivert.dll": b"dll-new",
        "bin/WinDivert64.sys": b"driver-new",
        "general (ALT13).bat": "echo winws.exe --wf-tcp=443 --dpi-desync=fake\n",
        "service.bat": "@echo off\necho service\n",
        "lists/list-general.txt": "general.new\n",
        "lists/list-exclude.txt": "exclude.new\n",
        "lists/ipset-all.txt": "1.1.1.1/32\n",
        "lists/list-general-user.txt": "MUST-NOT-REPLACE\n",
        "lists/list-exclude-user.txt": "MUST-NOT-REPLACE\n",
        "lists/ipset-exclude-user.txt": "MUST-NOT-REPLACE\n",
        "config.json": "MUST-NOT-REPLACE\n",
        "custom_strategies/own.bat": "MUST-NOT-REPLACE\n",
        "utils/game_filter.enabled": "MUST-NOT-REPLACE\n",
    }
    files.update(extra or {})
    return _zip_bytes(files)


def _source(tag: str, hosts="127.0.0.1 service.new") -> bytes:
    prefix = "Flowseal-zapret-source/"
    return _zip_bytes({
        prefix + ".service/hosts": hosts + "\n",
        prefix + ".service/ipset-service.txt": "2.2.2.0/24\n",
        prefix + ".service/version.txt": tag + "\n",
        prefix + "README.md": "source tree\n",
    })


def test_full_update_merges_service_data_preserves_users_and_removes_stale():
    from app import updater

    old_requests = updater.requests
    try:
        first_requests = _Requests({
            "asset-1": _asset({"utils/obsolete-upstream.bin": b"old"}),
            "source-1": _source("1.10.2"),
        })
        updater.requests = first_requests
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "zapret"
            (root / "lists").mkdir(parents=True)
            user_values = {
                "list-general-user.txt": "USER-GENERAL\n",
                "list-exclude-user.txt": "USER-EXCLUDE\n",
                "ipset-exclude-user.txt": "USER-IPSET\n",
            }
            for name, value in user_values.items():
                (root / "lists" / name).write_text(value, encoding="utf-8")
            (root / "config.json").write_text("USER-CONFIG\n", encoding="utf-8")
            (root / "custom_strategies").mkdir()
            (root / "custom_strategies" / "own.bat").write_text(
                "USER-STRATEGY\n", encoding="utf-8"
            )
            (root / "utils").mkdir()
            (root / "utils" / "game_filter.enabled").write_text(
                "USER-STATE\n", encoding="utf-8"
            )

            rel = updater.ReleaseInfo(
                "v1.10.2", "v1.10.2", "asset-1", "release",
                source_zip_url="source-1",
            )
            message = updater.download_and_apply(rel, root)
            assert "Обновлено до" in message, message
            assert (root / ".service" / "hosts").read_text() == "127.0.0.1 service.new\n"
            assert (root / ".service" / "ipset-service.txt").read_text() == "2.2.2.0/24\n"
            assert (root / "lists" / "list-general.txt").read_text() == "general.new\n"
            assert (root / "lists" / "list-exclude.txt").read_text() == "exclude.new\n"
            assert (root / "lists" / "ipset-all.txt").read_text() == "1.1.1.1/32\n"
            assert (root / "general (ALT13).bat").exists()
            assert (root / "service.bat").exists()
            for name, value in user_values.items():
                assert (root / "lists" / name).read_text() == value
            assert (root / "config.json").read_text() == "USER-CONFIG\n"
            assert (root / "custom_strategies" / "own.bat").read_text() == "USER-STRATEGY\n"
            assert (root / "utils" / "game_filter.enabled").read_text() == "USER-STATE\n"

            manifest = json.loads(
                (root / updater.MANIFEST_FILENAME).read_text(encoding="utf-8")
            )
            assert ".service/hosts" in manifest["files"]
            assert "service.bat" in manifest["files"]
            assert not any(name.endswith("-user.txt") for name in manifest["files"])
            catalog = json.loads((root / "strategies.json").read_text(encoding="utf-8"))
            assert any("ALT13" in item["name"] for item in catalog["strategies"])

            (root / "notes").mkdir()
            (root / "notes" / "local-only.txt").write_text("keep", encoding="utf-8")
            updater.requests = _Requests({
                "asset-2": _asset({"utils/new-upstream.bin": b"new"}),
                "source-2": _source("1.10.3", "127.0.0.1 service.v2"),
            })
            rel2 = updater.ReleaseInfo(
                "v1.10.3", "v1.10.3", "asset-2", "release",
                source_zip_url="source-2",
            )
            message2 = updater.download_and_apply(rel2, root)
            assert "Обновлено до" in message2, message2
            assert not (root / "utils" / "obsolete-upstream.bin").exists()
            assert (root / "utils" / "new-upstream.bin").read_bytes() == b"new"
            assert (root / "notes" / "local-only.txt").read_text() == "keep"
            for name, value in user_values.items():
                assert (root / "lists" / name).read_text() == value
    finally:
        updater.requests = old_requests


def test_list_update_merges_tagged_service_files_and_preserves_user_lists():
    from app import list_manager, updater

    old_requests = list_manager.requests
    old_latest = updater.latest_release
    try:
        list_manager.requests = _Requests({
            "asset": _asset(),
            "source": _source("1.10.2"),
        })
        updater.latest_release = lambda timeout=10.0: updater.ReleaseInfo(
            "v1.10.2", "v1.10.2", "asset", "release",
            source_zip_url="source",
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "lists").mkdir()
            user = root / "lists" / "list-general-user.txt"
            user.write_text("USER\n", encoding="utf-8")
            result = list_manager.update_zapret_lists(root)
            assert result.ok, result.message
            assert user.read_text() == "USER\n"
            assert (root / ".service" / "hosts").exists()
            assert (root / ".service" / "ipset-service.txt").exists()
            assert (root / ".service" / "version.txt").read_text() == "1.10.2\n"
    finally:
        list_manager.requests = old_requests
        updater.latest_release = old_latest


def test_embedded_install_records_manifest_without_overwriting_user_file():
    from app import bootstrap, updater

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        src = base / "vendor"
        dst = base / "installed"
        (src / "lists").mkdir(parents=True)
        (dst / "lists").mkdir(parents=True)
        (src / "lists" / "list-general.txt").write_text("UPSTREAM\n")
        (src / "lists" / "list-general-user.txt").write_text("PLACEHOLDER\n")
        (src / updater.INSTALLED_MARKER).write_text("1.10.2")
        (src / updater.INSTALLED_SHA256_MARKER).write_text("abc123")
        user = dst / "lists" / "list-general-user.txt"
        user.write_text("USER\n")
        assert bootstrap._install_from_bundle(src, dst) == 1
        assert user.read_text() == "USER\n"
        assert updater.local_version(dst) == "1.10.2"
        assert updater._load_installed_sha256(dst) == "abc123"
        manifest = json.loads((dst / updater.MANIFEST_FILENAME).read_text())
        assert manifest["files"] == ["lists/list-general.txt"]


def test_build_fetch_validates_hidden_service_and_complete_runtime_data():
    text = Path("fetch_zapret.ps1").read_text(encoding="utf-8")
    assert "Get-ChildItem -LiteralPath $srcRoot -Force" in text
    assert "Copy-Item -LiteralPath $serviceDir.FullName" in text
    assert "$headers['Authorization']" in text
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in workflow
    for required in (
        ".service\\hosts",
        ".service\\ipset-service.txt",
        "lists\\list-general.txt",
        "lists\\list-exclude.txt",
        "lists\\ipset-all.txt",
        "service.bat",
    ):
        assert required in text
