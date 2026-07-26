# Чек-лист выпуска релиза Zapret GUI

Документ описывает то, как релиз делается **сейчас**: сборка exe через
PyInstaller, установщик Inno Setup, публикация установщика на GitHub и
обновление у пользователей кнопкой «Обновить приложение» внутри программы.

Окружение разработчика (для справки):

- Python 3.14 (`C:\Python314\python.exe`), PyQt6, Windows.
- Git: `C:\Users\Administrator\PortableGit\cmd\git.exe` (может отсутствовать в PATH).
- Inno Setup: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.

---

## 1. Проверка кода и тестов

Перед сборкой обязательно удалить кэш Python (`__pycache__`), иначе тесты могут
упасть с ошибкой доступа к памяти.

```bat
python tools/check_lint.py
python -m pytest tests/ -q
```

Эталон:

- `check_lint.py` печатает `pyflakes: clean (1 known finding ignored, ... files checked)`.
  Единственное разрешённое замечание — строка `import app.tg_proxy  # noqa: F401`
  в `tests/test_tg_proxy_logic.py`. Вендорная папка `app/tg_proxy_engine/` не
  проверяется вообще.
- pytest: все тесты проходят (`... passed`).

Если `check_lint.py` печатает `pyflakes found new issues` — релиз не собираем,
сначала правим код.

## 2. Поднять версию

Версия правится **только** в файле `VERSION` в корне проекта (одна строка вида
`1.8.5`). Дальше она разъезжается автоматически:

- `app/__init__.py` читает `VERSION` (`app.__version__`);
- `build_installer.bat` читает `VERSION` и передаёт её в ISCC как
  `/DMyAppVersion=<версия>`;
- `installer.iss` кладёт файл `VERSION` рядом с exe при установке;
- `app/self_updater.py` читает эту установленную копию, чтобы понять, какая
  версия стоит у пользователя.

Нигде больше версию руками писать не нужно.

## 3. Сборка exe

Перед сборкой закрыть работающий ZapretGUI (в том числе иконку в трее) и
установленную копию — Windows держит exe заблокированным.

```bat
python -m PyInstaller zapret-gui.spec --noconfirm --clean
```

Если `dist\ZapretGUI.exe` занят, сборку можно перенаправить:

```bat
python -m PyInstaller zapret-gui.spec --noconfirm --clean --distpath dist_release
```

## 4. Сборка установщика

```bat
build_installer.bat
```

или вручную (версию подставить из `VERSION`, путь к exe — если собирали в
`dist_release`):

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.8.5 /DMyAppExeSource="dist_release\ZapretGUI.exe" installer.iss
```

Результат: `Output\ZapretGUI-Setup.exe`.

## 5. Проверка перед публикацией

- [ ] Установщик запускается, устанавливает программу в `C:\Program Files\ZapretGUI\`.
- [ ] Рядом с exe появился файл `VERSION` с новой версией. **Без него**
      программа будет предлагать одно и то же обновление бесконечно.
- [ ] Программа запускается, обход работает, темы переключаются.
- [ ] Галочка автозапуска в установщике создаёт задачу в планировщике и не
      вызывает запрос UAC при входе в Windows.

## 6. Один чистый коммит

Все правки релиза уходят одним осмысленным коммитом (не серией мелких).
Опубликованную историю не переписываем.

```bat
git add -A
git commit -m "release: 1.8.5 — краткое описание"
git push origin main
```

Дождаться, что автопроверка на GitHub (`.github/workflows/tests.yml`) стала
зелёной.

## 7. Контрольная сумма установщика

```bat
python -c "import hashlib;print(hashlib.sha256(open(r'Output/ZapretGUI-Setup.exe','rb').read()).hexdigest())"
```

Сумму обязательно вставить в описание релиза.

## 8. Публикация релиза на GitHub

- Тег: `vX.Y.Z` (совпадает с `VERSION`).
- Приложить файл **`ZapretGUI-Setup.exe`** — имя менять нельзя, встроенное
  обновление ищет ровно такое имя (`INSTALLER_ASSET` в `app/self_updater.py`).
- В описание добавить:
  - что изменилось;
  - SHA-256 установщика;
  - требование Windows и права администратора (нужны для WinDivert);
  - предупреждение о ложных срабатываниях антивируса на WinDivert/winws;
  - ссылку на исходный проект zapret-discord-youtube.
- Токен для публикации брать из `git credential fill`. Токен **никогда** не
  печатать в чат, в логи и в файлы.

## 9. Проверка обновления «как у пользователя»

Обязательный шаг: обновление ломалось дважды.

- [ ] Установить **предыдущую** версию, запустить, нажать «Обновить приложение».
- [ ] Обновление скачивается, показывает совпадение SHA-256, установщик
      запускается и НЕ убивает сам себя.
- [ ] После установки программа открывается уже в новой версии, и повторно
      обновление не предлагается.

Важно: если у файла установщика на GitHub нет опубликованной контрольной суммы,
программа откажется ставить обновление — это защита, а не ошибка.

## 10. Лицензии и атрибуция (проверять при каждом релизе)

- [ ] Исходники остаются под GPL-3.0 (требование PyQt6).
- [ ] Не коммитить `vendor/zapret/bin`, скачанные архивы, `dist`, `build`,
      локальные настройки и логи.
- [ ] Сохранены ссылки и упоминания:
  - Flowseal/zapret-discord-youtube — https://github.com/Flowseal/zapret-discord-youtube
  - bol-van/zapret — https://github.com/bol-van/zapret
  - WinDivert — https://github.com/basil00/WinDivert
- [ ] В README нет намёка на связь с Discord/YouTube/Flowseal/bol-van.
- [ ] `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md` на месте и попадают в
      установку.
- [ ] Логотипы и названия Discord/YouTube не используются в оформлении.
