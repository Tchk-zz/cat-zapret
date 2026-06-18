# Zapret GUI v38 audit report

Date: 2026-06-18

## Scope

Audited the provided `zapret-gui-v38-fixed.zip` source package for GitHub readiness,
common runtime errors, dependency/licensing risks, and basic functional integrity.

## What was checked

- Project structure and source files.
- Python syntax compilation.
- JSON validity for the strategy catalog.
- Importability of non-Qt application modules in the sandbox.
- Static scan for obvious secrets/tokens and high-risk command execution.
- Build/installer scripts and PyInstaller spec.
- Third-party licensing implications for Flowseal zapret-discord-youtube, bol-van zapret, WinDivert and PyQt6.
- Repository hygiene files required before publishing.

## Results

### Passed

- `python -m compileall -q .` passes.
- `vendor/strategies.json` is valid JSON and loads 20 strategies.
- Core non-UI modules import successfully: config, strategy manager/catalog, exclusions, connectivity, updater, bootstrap, service manager, autostart, auto selector, process runner.
- No hardcoded API keys, tokens, private keys or passwords were found by the static scan.
- Subprocess calls use argument lists (`shell=False`), which is good.
- Build scripts are understandable and fetch the upstream Flowseal bundle only during build if it is not already present.

### Fixed in the prepared GitHub package

- Added repository hygiene and legal files: `.gitignore`, `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `SECURITY.md`, `CONTRIBUTING.md`, issue templates and release checklist.
- Added basic unit tests for core strategy/exclusion logic.
- Fixed domain normalization for custom include/exclude entries: pasted URLs like `https://example.com/path` are now normalized to `example.com` before writing zapret hostlists.

### Limitations

- Full GUI launch and `winws.exe` runtime behavior could not be tested in this Linux sandbox because the app is Windows/PyQt6/WinDivert-based.
- PyQt6 and Windows-only modules were not installed in the sandbox at the start; non-UI logic was tested separately.
- Actual bypass effectiveness depends on provider/network conditions and must be tested on Windows 10/11 with administrator rights.

## Important licensing conclusion

Use **GPL-3.0** for this repository unless you have a commercial PyQt license.
PyQt6 is GPL-3.0/commercial, so publishing a PyQt6 app as MIT/proprietary is risky.
Flowseal and bol-van zapret are MIT-compatible, but PyQt6 is the license that forces the GUI repository toward GPL-3.0.

## Recommended GitHub strategy

- Publish only source code and build scripts in the repository.
- Do not commit downloaded `vendor/zapret` binaries.
- For releases, include attribution and third-party notices with the `.exe`.
- Make the README clear that this is an independent GUI for Flowseal's zapret-discord-youtube, not an official Flowseal/bol-van project.
