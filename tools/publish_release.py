"""Publish a GitHub release for Zapret GUI straight from the repository.

The script talks to the GitHub REST API and takes the token from Git's own
credential store -- the very same credential ``git push`` already uses. On a CI
runner there is no credential store, so GH_TOKEN / GITHUB_TOKEN is used when it
is set. The token is never printed and never written to disk. Nothing else is
required: no GitHub CLI, no manual clicking in the browser.

Usage:
    python tools/publish_release.py                 # version from VERSION
    python tools/publish_release.py --version 1.9.3
    python tools/publish_release.py --dry-run       # show notes, publish nothing

Steps:
  1. read the version (VERSION file or --version) -> tag name vX.Y.Z;
  2. require Output/ZapretGUI-Setup.exe and compute its SHA-256;
  3. take the matching section out of CHANGELOG.md as the release notes and
     append the SHA-256 block the release checklist requires;
  4. create the release (or reuse it when the tag is already published) and
     upload the installer under the exact name ZapretGUI-Setup.exe.

Why the exact asset name matters: app/self_updater.py looks the asset up by
that name and refuses to run an installer whose sha256 digest GitHub did not
publish, so a renamed asset silently breaks in-app updates for everyone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
REPO = "Tchk-zz/cat-zapret"
ASSET_NAME = "ZapretGUI-Setup.exe"
ASSET_PATH = ROOT / "Output" / ASSET_NAME
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


def _token():
    """Return the GitHub token. Never logged, never stored.

    Order matters. On GitHub Actions the workflow hands the token over through
    GH_TOKEN (or the built-in GITHUB_TOKEN) and there is no credential helper to
    ask, while on a developer machine the credential ``git push`` already saved
    is reused, so nothing has to be configured by hand.
    """
    for env_name in ("GH_TOKEN", "GITHUB_TOKEN"):
        env_token = (os.environ.get(env_name) or "").strip()
        if env_token:
            return env_token
    res = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if res.returncode != 0:
        raise SystemExit(
            "git credential fill failed: " + (res.stderr.strip() or "no output")
        )
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise SystemExit(
        "No github.com token: neither GH_TOKEN in the environment nor a saved "
        "credential. Do one `git push` first so the credential helper saves it."
    )


def _call(
    method,
    url,
    token,
    data=None,
    content_type="application/json",
    raw=False,
    allow_404=False,
):
    """Minimal GitHub API call. Returns the parsed body, or {} when empty."""
    body = None
    if data is not None:
        body = data if raw else json.dumps(data).encode("utf-8")
    req = request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "zapret-gui-release-script")
    if body is not None:
        req.add_header("Content-Type", content_type)
    try:
        with request.urlopen(req) as resp:
            text = resp.read().decode("utf-8", "replace")
    except error.HTTPError as exc:
        if exc.code == 404 and allow_404:
            return None
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}\n{detail}")
    except error.URLError as exc:
        raise SystemExit(f"{method} {url} -> network error: {exc.reason}")
    return json.loads(text) if text.strip() else {}


def _changelog_section(version):
    """Return the CHANGELOG.md body for this version, heading excluded."""
    path = ROOT / "CHANGELOG.md"
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    head = "## [" + version + "]"
    start = next((i for i, ln in enumerate(lines) if ln.startswith(head)), None)
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ["):
            end = j
            break
    return "\n".join(lines[start + 1:end]).strip()


def _notes(version, digest):
    body = _changelog_section(version) or ("Версия " + version + ".")
    return (
        body
        + "\n\n### Проверка целостности\n\n"
        + "SHA-256 `" + ASSET_NAME + "`:\n\n```\n" + digest + "\n```\n\n"
        + "Проверить скачанный файл (PowerShell):\n\n```powershell\n"
        + "Get-FileHash .\\" + ASSET_NAME + " -Algorithm SHA256\n```\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Publish a Zapret GUI release.")
    parser.add_argument("--version", default=None, help="default: VERSION file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--prerelease", action="store_true")
    args = parser.parse_args()

    version = (
        args.version or (ROOT / "VERSION").read_text(encoding="utf-8")
    ).strip()
    tag = "v" + version
    if not ASSET_PATH.exists():
        raise SystemExit(f"{ASSET_PATH} is missing. Run build_installer.bat first.")
    blob = ASSET_PATH.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    notes = _notes(version, digest)
    print(f"tag:    {tag}")
    print(f"asset:  {ASSET_PATH} ({len(blob) / 1048576:.1f} MB)")
    print(f"sha256: {digest}")
    if args.dry_run:
        print("--- release notes ---")
        print(notes)
        return 0

    token = _token()
    release = _call(
        "GET", f"{API}/repos/{REPO}/releases/tags/{tag}", token, allow_404=True
    )
    fields = {
        "tag_name": tag,
        "name": "Zapret GUI " + version,
        "body": notes,
        "draft": False,
        "prerelease": bool(args.prerelease),
    }
    if release:
        release = _call(
            "PATCH", f"{API}/repos/{REPO}/releases/{release['id']}", token, fields
        )
        print("updated the existing release")
    else:
        release = _call("POST", f"{API}/repos/{REPO}/releases", token, fields)
        print("created the release")

    # Re-uploading over an existing asset is an error, so drop the old copy.
    # Query the assets endpoint explicitly: interrupted uploads remain in the
    # ``starter`` state and are not always included in the release payload.
    assets = _call(
        "GET", f"{API}/repos/{REPO}/releases/{release['id']}/assets", token
    ) or []
    for asset in assets:
        if asset.get("name") == ASSET_NAME:
            _call(
                "DELETE", f"{API}/repos/{REPO}/releases/assets/{asset['id']}", token
            )
            print("removed the previous copy of the asset")

    uploaded = _call(
        "POST",
        f"{UPLOADS}/repos/{REPO}/releases/{release['id']}/assets?name={ASSET_NAME}",
        token,
        blob,
        content_type="application/octet-stream",
        raw=True,
    ) or {}
    print("upload: " + str(uploaded.get("browser_download_url", "?")))
    published = str(uploaded.get("digest") or "").lower()
    if published != "sha256:" + digest:
        print(
            "WARNING: GitHub has not published a matching sha256 digest yet "
            f"(got {published or 'nothing'}). The in-app updater refuses to "
            "install an asset without it -- re-check the release page."
        )
    print("release: " + str(release.get("html_url", "?")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
