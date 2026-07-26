# Third-party notices

This project includes or depends on third-party software. Keep this file updated
when dependencies change.

## zapret-discord-youtube by Flowseal

- Repository: https://github.com/Flowseal/zapret-discord-youtube
- Role: source of Windows zapret bundle, strategies, lists and `winws.exe` used by the GUI.
- License: MIT, according to the upstream repository license section.
- Required action when distributing binaries that include the bundle: include the upstream MIT license/copyright notice and keep attribution in README/NOTICE.

## tg-ws-proxy by Flowseal

- Repository: https://github.com/Flowseal/tg-ws-proxy
- Role: source of the local Telegram MTProto proxy engine. ZapretGUI embeds
  the upstream `proxy/` and `utils/` Python modules verbatim under
  `app/tg_proxy_engine/` and runs the engine as an asyncio task inside its
  own process (no separate `TgWsProxy.exe` subprocess, no second tray icon).
- License: MIT. The full license text and copyright notice are included at
  `app/tg_proxy_engine/LICENSE`.
- Required action when distributing binaries: keep the LICENSE file inside
  `app/tg_proxy_engine/` and the attribution in README/NOTICE/this file.
  The upstream tray-UI files (`windows.py`, `macos.py`, `linux.py`, `ui/`,
  `utils/tray_common.py`, `utils/update_check.py`, `utils/win32_theme.py`)
  are NOT included in this redistribution.

## zapret by bol-van

- Repository: https://github.com/bol-van/zapret
- Role: original DPI bypass project used by Flowseal's bundle.
- License: MIT, according to `docs/LICENSE.txt` in the upstream repository.
- Required action: preserve copyright and license notices.

## WinDivert by basil00 / ReQrypt

- Repository: https://github.com/basil00/WinDivert
- Website: https://reqrypt.org/windivert.html
- Role: Windows packet interception driver/library used by zapret/winws.
- License: WinDivert documentation describes it as LGPL-3.0, and current project pages also mention dual LGPL/GPL choices depending on distribution.
- Required action: include WinDivert license text/notices when shipping binaries that contain WinDivert files. Do not remove upstream license files from the downloaded bundle.

## PyQt6 by Riverbank Computing

- Package: https://pypi.org/project/PyQt6/
- Role: GUI toolkit bindings.
- License: GPL-3.0 or commercial Riverbank license.
- Project decision: this repository uses GPL-3.0 for compatibility with the GPL version of PyQt6. If you want a non-GPL/proprietary license, buy a commercial PyQt license or migrate to PySide6 and verify Qt licensing.

## Other Python dependencies

- `requests` — Apache-2.0
- `cryptography` — Apache-2.0 or BSD-style dual license (used by the embedded
  tg-ws-proxy engine for MTProto encryption)
- `pywin32` — Python Software Foundation / BSD-style license
- Transitive dependencies may include `urllib3`, `certifi`, `idna`, and `charset-normalizer`.

When publishing releases, verify the exact wheel versions and include their
license notices if they are bundled into the executable by PyInstaller.
