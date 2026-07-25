# GitHub release checklist

## 1. Before publishing the repository

- [ ] Decide the public name (`zapret-gui` is clear and searchable).
- [ ] Keep the repository public source code under GPL-3.0 because PyQt6 is GPL-3.0 unless you buy a commercial PyQt license.
- [ ] Do **not** commit `vendor/zapret/bin`, downloaded Flowseal archives, `dist`, `build`, local configs, or logs.
- [ ] Keep links and attribution to:
  - Flowseal/zapret-discord-youtube — https://github.com/Flowseal/zapret-discord-youtube
  - bol-van/zapret — https://github.com/bol-van/zapret
  - WinDivert — https://github.com/basil00/WinDivert
- [ ] Review README wording: do not imply affiliation with Discord/YouTube/Flowseal/bol-van.
- [ ] If you publish Windows binaries, include `LICENSE`, `NOTICE`, and `THIRD_PARTY_NOTICES.md` in the release archive/installer.

## 2. Local validation

```bat
python -m compileall .
python -m unittest discover -s tests
build.bat
```

Optional installer:

```bat
build_installer.bat
```

## 3. Create the GitHub repository

```bash
git init
git add .
git commit -m "Initial public release"
git branch -M main
git remote add origin https://github.com/<your-user>/zapret-gui.git
git push -u origin main
```

## 4. Create a release

1. Build `dist\\ZapretGUI.exe` on a clean Windows machine.
2. Scan the release archive with antivirus/VirusTotal if possible.
3. Create `ZapretGUI-vX.Y.Z.zip` containing:
   - `ZapretGUI.exe`
   - `README.md`
   - `LICENSE`
   - `NOTICE`
   - `THIRD_PARTY_NOTICES.md`
4. Draft release notes with:
   - what changed;
   - Windows requirement;
   - admin-rights explanation;
   - antivirus false-positive note for WinDivert/winws;
   - link to upstream zapret-discord-youtube.

## 5. To reduce takedown/complaint risk

- Avoid using Discord/YouTube logos or names in your project branding.
- State that the project is an independent GUI/wrapper.
- Preserve all upstream licenses.
- If an upstream author asks for attribution wording changes, comply quickly.
- Do not sell builds that contain third-party binaries unless you have reviewed all licenses carefully.
