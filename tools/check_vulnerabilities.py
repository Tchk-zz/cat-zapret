"""Fail when an installed direct runtime dependency has an OSV advisory.

The check uses the versions actually installed by CI, not only requirement
ranges. It performs one free OSV querybatch request and never uploads source or
user data.
"""
from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import requests

OSV_BATCH_API = "https://api.osv.dev/v1/querybatch"
ROOT = Path(__file__).resolve().parent.parent
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def direct_runtime_packages(path: Path) -> list[tuple[str, str]]:
    packages = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "http:")) or line.startswith("https:"):
            continue
        match = _REQUIREMENT_NAME.match(line)
        if not match:
            continue
        name = match.group(1)
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise SystemExit(f"Runtime dependency is not installed: {name}") from exc
        packages.append((name, version))
    return packages


def main() -> int:
    packages = direct_runtime_packages(ROOT / "requirements.txt")
    payload = {
        "queries": [
            {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
            for name, version in packages
        ]
    }
    response = requests.post(OSV_BATCH_API, json=payload, timeout=30)
    response.raise_for_status()
    results = response.json().get("results", [])
    findings = []
    for (name, version), result in zip(packages, results):
        for vuln in result.get("vulns", []):
            findings.append((name, version, vuln.get("id", "unknown")))
    if findings:
        print("OSV vulnerabilities found in direct runtime dependencies:")
        for name, version, vuln_id in findings:
            print(f"- {name}=={version}: {vuln_id}")
        return 1
    print("OSV: clean (" + ", ".join(f"{n}=={v}" for n, v in packages) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
