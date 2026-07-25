import subprocess, sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('=== PyInstaller ===')
r = subprocess.run(
    [sys.executable, '-m', 'PyInstaller', 'zapret-gui.spec',
     '--noconfirm', '--distpath', 'dist_release', '--workpath', 'build_release'],
    capture_output=True, text=True
)
print(r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout)
if r.returncode != 0:
    print('STDERR:', r.stderr[-1000:])
    sys.exit(r.returncode)
print('exit=0 PyInstaller OK')

print('=== ISCC ===')
ISSC = r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
r2 = subprocess.run(
    [ISSC, '/Qp', '/DMyAppVersion=1.8.0', '/DMyAppExeSource=dist_release\\ZapretGUI.exe', 'installer.iss'],
    capture_output=True, text=True
)
print(r2.stdout)
if r2.returncode != 0:
    print('ISCC STDERR:', r2.stderr[-500:])
    sys.exit(r2.returncode)
print('exit=0 ISCC OK')
