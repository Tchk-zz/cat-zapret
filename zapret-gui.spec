# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Zapret GUI.
# Build with:  pyinstaller zapret-gui.spec

import os


def _collect_zapret(src_root, dest_root='zapret'):
    """Collect every file under vendor/zapret as PyInstaller (src, dest) data."""
    items = []
    if os.path.isdir(src_root):
        for dirpath, _dirs, files in os.walk(src_root):
            for f in files:
                full = os.path.join(dirpath, f)
                reldir = os.path.relpath(dirpath, src_root)
                dest = dest_root if reldir == '.' else os.path.join(dest_root, reldir)
                items.append((full, dest))
    return items


# The whole Flowseal zapret bundle (bin/, lists/, *.bat) is embedded into the
# exe. build.bat downloads it into vendor/zapret before PyInstaller runs, so
# the finished app is fully self-contained.
zapret_datas = _collect_zapret(os.path.join(SPECPATH, 'vendor', 'zapret'))

# Prebuilt strategy catalog (generated from Flowseal's .bat at build time).
# Shipping it means the strategy list is available immediately, and the app
# never has to parse foreign .bat on a normal launch.
_seed_catalog = os.path.join(SPECPATH, 'vendor', 'strategies.json')
if os.path.isfile(_seed_catalog):
    zapret_datas.append((_seed_catalog, '.'))

# App VERSION file. Kept at the app root for the installer / About screens.
_version_file = os.path.join(SPECPATH, 'VERSION')
if os.path.isfile(_version_file):
    zapret_datas.append((_version_file, '.'))

# Embedded tg-ws-proxy engine VERSION. This is intentionally separate from the
# ZapretGUI app version because the proxy engine can update independently.
_tg_engine_version = os.path.join(SPECPATH, 'app', 'tg_proxy_engine', 'VERSION')
if os.path.isfile(_tg_engine_version):
    zapret_datas.append((_tg_engine_version, os.path.join('app', 'tg_proxy_engine')))

# Roblox bypass profile — a JSON file users can edit (e.g. when Roblox adds
# new game-server IP subnets) without rebuilding the exe. Loaded at runtime
# by app.bootstrap.load_roblox_profile(). Without this entry the app would
# silently fall back to the hardcoded _ROBLOX_FIX_ARGS string (still works,
# but edits to the JSON would have no effect in the frozen build).
_roblox_profile = os.path.join(SPECPATH, 'roblox_profile.json')
if os.path.isfile(_roblox_profile):
    zapret_datas.append((_roblox_profile, '.'))

# UI assets (the exact gradient background, etc.) bundled into the exe so the
# interface looks identical to the design without any external files.
_ui_assets = os.path.join(SPECPATH, 'ui', 'assets')
if os.path.isdir(_ui_assets):
    for _f in os.listdir(_ui_assets):
        _full = os.path.join(_ui_assets, _f)
        if os.path.isfile(_full):
            zapret_datas.append((_full, os.path.join('ui', 'assets')))

# Bundled fonts (Unbounded). The loop above only grabs files directly in
# ui/assets, so the nested fonts/ folder is collected separately here.
_ui_fonts = os.path.join(SPECPATH, 'ui', 'assets', 'fonts')
if os.path.isdir(_ui_fonts):
    for _f in os.listdir(_ui_fonts):
        _full = os.path.join(_ui_fonts, _f)
        if os.path.isfile(_full):
            zapret_datas.append((_full, os.path.join('ui', 'assets', 'fonts')))

# Theme background images (under ui/assets/themes/). Used by the 7 image themes
# (Mist, Azure, Snow, Lavender, Fog, Sand, Midnight). Each .jpg is shipped
# verbatim and loaded by GradientBackground.set_theme_image() at runtime.
_theme_imgs = os.path.join(SPECPATH, 'ui', 'assets', 'themes')
if os.path.isdir(_theme_imgs):
    for _f in os.listdir(_theme_imgs):
        _full = os.path.join(_theme_imgs, _f)
        if os.path.isfile(_full):
            zapret_datas.append((_full, os.path.join('ui', 'assets', 'themes')))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=zapret_datas,
    hiddenimports=['win32api', 'win32con', 'win32service', 'win32serviceutil', 'logging.handlers', 'concurrent.futures.thread'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ZapretGUI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,           # request elevation (WinDivert needs admin)
    icon=os.path.join(SPECPATH, 'ui', 'assets', 'app.ico'),
)
