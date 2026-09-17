# Third-party notices

Zapret GUI includes, downloads, or builds against third-party software. Copyright
and license terms remain with the respective authors. Keep the corresponding
upstream license files when redistributing a build.

> This overview is informational. The license text supplied by each upstream
> project is authoritative.

## Flowseal / zapret-discord-youtube

- Repository: https://github.com/Flowseal/zapret-discord-youtube
- Role: Windows Zapret bundle, strategies, lists, `winws.exe`, WinDivert files and
  supporting utilities synchronized by the application.
- License: MIT; see upstream `LICENSE.txt`.
- Distribution note: preserve the upstream copyright and MIT permission notice.

## bol-van / zapret

- Repository: https://github.com/bol-van/zapret
- Role: original DPI-circumvention project underlying the Windows bundle.
- License: MIT; see upstream `docs/LICENSE.txt`.
- Distribution note: preserve the upstream copyright and license notice.

## Flowseal / tg-ws-proxy

- Repository: https://github.com/Flowseal/tg-ws-proxy
- Role: source of the embedded Telegram MTProto WebSocket proxy engine.
- License: MIT.
- Local copy: selected upstream `proxy/` and `utils/` modules are maintained under
  `app/tg_proxy_engine/`; the full notice is stored in
  `app/tg_proxy_engine/LICENSE`.
- Distribution note: keep that LICENSE file inside packaged applications. The
  upstream platform tray front ends are not redistributed here.

## WinDivert by basil00 / ReQrypt

- Repository: https://github.com/basil00/WinDivert
- Website: https://reqrypt.org/windivert.html
- Role: Windows packet interception driver and library used by `winws.exe`.
- License: GNU Lesser General Public License, version 3; consult the current
  upstream `LICENSE` for the exact terms and any available licensing options.
- Distribution note: retain the license and copyright notices shipped with the
  WinDivert binaries and source bundle.

## PyQt6 by Riverbank Computing

- Package: https://pypi.org/project/PyQt6/
- Role: Python bindings used for the graphical interface.
- License: GPL-3.0 or a commercial Riverbank license.
- Project choice: Zapret GUI is distributed as GPL-3.0-only while using the GPL
  edition of PyQt6.

## Python runtime and build dependencies

| Package | Role | License summary |
|---|---|---|
| `requests` | HTTPS and API downloads | Apache-2.0 |
| `cryptography` | MTProto cryptography | Apache-2.0 OR BSD-3-Clause |
| `pywin32` | Windows APIs | PSF and BSD-style terms; see package notices |
| `PyInstaller` | Release packaging | GPL-2.0-or-later with the upstream bootloader exception |
| `pytest`, `pytest-qt`, `pyflakes` | Tests and static checks | Development-only; see each package metadata |

PyInstaller may bundle transitive packages such as `urllib3`, `certifi`, `idna`
and `charset-normalizer`. Release maintainers must review the exact dependency
set and preserve all notices required by the wheels included in the executable.

## Maintainer checklist

When an upstream component or pinned dependency changes:

1. inspect the license in the exact downloaded tag or wheel;
2. update this file if the attribution or terms changed;
3. keep required license files in the installer;
4. verify that GPL-compatible distribution remains possible.
