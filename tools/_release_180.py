import subprocess, sys, json, os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- get token ---
r = subprocess.run(
    ["git", "credential", "fill"],
    input="protocol=https\nhost=github.com\n\n",
    capture_output=True, text=True
)
token = ""
for line in r.stdout.splitlines():
    if line.startswith("password="):
        token = line[9:].strip()
        break
if not token:
    sys.exit("No token")

import urllib.request, urllib.error

HEADERS = {
    "Authorization": "Bearer " + token,
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
}

REPO = "Tchk-zz/cat-zapret"
VER  = "v1.8.0"

# --- tag ---
subprocess.run(["git", "tag", VER], capture_output=True)
subprocess.run(["git", "push", "origin", VER], capture_output=True)

# --- create release ---
body_lines = [
    "## v1.8.0",
    "",
    "### Что изменилось",
    "**Рефакторинг и стабильность:**",
    "- `ui/main_window.py` распилен: 5323 → 2072 строки; каждая вкладка — отдельный файл (`tab_home`, `tab_telegram`, `tab_games`, `tab_strategy`, `tab_settings`)",
    "- `ui/theme.py` разделён на `fonts.py`, `qss.py`, `gradient_background.py`",
    "- Выделены `ui/i18n.py` (переводы), `ui/widgets_custom.py` (виджеты), `ui/paths.py` (поиск ресурсов)",
    "- Убраны ~250 лишних импортов; статический анализатор `pyflakes` теперь находит ошибки до запуска",
    "",
    "**Исправления (из предыдущих итераций):**",
    "- Одно окно — одна копия приложения (мьютекс; повторный запуск фокусирует уже открытое)",
    "- Автоматическое масштабирование окна под Full HD и другие разрешения",
    "- Правильная иконка в панели задач (AppUserModelID)",
    "- Тёмная тема: исправлен краш при смене тем (`_Dark3DPanel has been deleted`)",
    "- Параллельные пробы серверов + отменяемость автоподбора",
    "- Поддержка 10 тем оформления",
    "",
    "**Обновлено:** ядро zapret до v1.10.0",
    "",
    "Добавлен файл `ЗАПУСК.bat` — двойной клик для запуска без консоли.",
]
body = "\n".join(body_lines)

payload = json.dumps({"tag_name": VER, "name": VER, "body": body, "draft": False, "prerelease": False}).encode()
url = "https://api.github.com/repos/" + REPO + "/releases"
req = urllib.request.Request(url, data=payload, headers=HEADERS, method="POST")
try:
    with urllib.request.urlopen(req) as resp:
        release = json.loads(resp.read())
except urllib.error.HTTPError as e:
    sys.exit("Create release failed: " + e.read().decode())

release_id = release["id"]
print("Release created:", release["html_url"])

# --- upload installer ---
ASET = "Output/ZapretGUI-Setup.exe"
if not os.path.exists(ASET):
    sys.exit("Installer not found: " + ASET)

with open(ASET, "rb") as fh:
    data = fh.read()

up_url = (
    "https://uploads.github.com/repos/" + REPO
    + "/releases/" + str(release_id)
    + "/assets?name=ZapretGUI-Setup.exe"
)
up_headers = dict(HEADERS)
up_headers["Content-Type"] = "application/octet-stream"
req2 = urllib.request.Request(up_url, data=data, headers=up_headers, method="POST")
try:
    with urllib.request.urlopen(req2) as resp2:
        asset = json.loads(resp2.read())
except urllib.error.HTTPError as e:
    sys.exit("Upload failed: " + e.read().decode())

print("Asset uploaded:", asset["browser_download_url"])
print("Size:", asset["size"], "bytes")
