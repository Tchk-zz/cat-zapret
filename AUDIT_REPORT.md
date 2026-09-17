# Аудит Cat Zapret — рабочий отчёт

Дата начала: 2026-09-17  
Исходный commit: `8d31f5b` (`main`, синхронизирован с `origin/main`)  
Версия приложения: `1.9.2`

## Baseline

- Windows 11, Python 3.14.6.
- Исходное состояние git было чистым.
- Исходный прогон: **222 tests passed**, pyflakes clean (1 заранее разрешённая находка).
- После интеграции с `origin/main` и текущей серии исправлений: **241 tests passed**, pyflakes clean (73 файла проверено), direct runtime dependencies OSV clean.
- Workflow YAML проверен парсером; CI теперь тестирует Python 3.10 и 3.14 на Windows.

## Upstream gap

### Flowseal/zapret-discord-youtube

- Проверен официальный latest release API: актуальный релиз — **1.10.2**, опубликован 2026-08-24.
- Release asset `zapret-discord-youtube-1.10.2.zip`: SHA-256 `5eaac9fb2e4b1abd693487452a3ff3f4dfe9578a45f9ddddfa4bc1f5a6bb62d5`.
- В 1.10.2 добавлена стратегия `ALT13`, исправлена загрузка Discord, улучшена диагностика, обновлены `list-general` и `list-exclude`.
- Локальный vendored bundle заметно старее: отсутствуют `general (ALT13).bat`, `general (EXP).bat`, новые QUIC/TLS/STUN шаблоны (`ACTIVE_*`, `stun2.bin`, 5ka/rutube/steamcommunity/tencent/sochi-park и др.), а также `.service/*`.
- Система обновления действительно скачивает **полный ZIP**, а не только `winws.exe`, но до аудита писала файлы прямо поверх активной установки, не удаляла устаревшие файлы и могла оставить смешанную версию после сбоя.

Источник: https://api.github.com/repos/Flowseal/zapret-discord-youtube/releases/latest

### Flowseal/tg-ws-proxy

- Встроенная версия: **1.7.3**.
- Актуальный release: **v1.10.2**, опубликован 2026-09-07; между версиями 71 upstream commit.
- Из основных модулей полностью совпадали с v1.10.2 только `_aes.py`, `fake_tls.py` и `logging_setup.py`; остальные разошлись.
- Upstream добавил ротацию/возраст WS-пула, exponential backoff, domain fronting, фрагментированные WebSocket messages, ограничения размера frame/message, улучшенную работу CF Worker pool и причины закрытия сессий.
- Важное расхождение безопасности: upstream v1.10.2 выставляет `ssl.CERT_NONE` и `check_hostname=False`. В Cat Zapret проверка сертификата уже была включена; переносить это небезопасное изменение нельзя.
- До аудита runtime updater скачивал source zipball без опубликованного SHA-256 и заменял `.py` по одному, из-за чего сбой мог оставить смесь версий; удалённые upstream-модули также могли оставаться.

Источник: https://api.github.com/repos/Flowseal/tg-ws-proxy/releases/latest

## Подтверждённые находки и исправления

### 1. Неполная/смешанная установка Telegram engine — High

**Проблема:** файлы обновлялись по одному непосредственно в активной runtime-папке. Сбой в середине оставлял несовместимый набор модулей, после чего версия могла быть отмечена новой.

**Исправлено:**
- распаковка теперь идёт в staging-каталог;
- введён обязательный полный набор основных модулей;
- ограничены размер загрузки, число файлов и суммарный распакованный размер;
- запрещены зашифрованные ZIP entries;
- все `.py` компилируются до установки;
- активная папка меняется directory swap с backup/rollback;
- backup удаляется только после успешной установки;
- конфигурация TLS принудительно остаётся безопасной (`CERT_REQUIRED`, hostname verification).

Файл: `app/tg_proxy.py`.

### 2. Неограниченные WebSocket frame/message — High

**Проблема:** peer мог объявить огромный frame, после чего код пытался прочитать/удержать его целиком; фрагментированные сообщения обрабатывались некорректно.

**Исправлено:**
- лимит 16 MiB проверяется до чтения payload;
- реализована сборка continuation frames;
- контролируется суммарный размер сообщения;
- сохранена строгая TLS-проверка, несмотря на небезопасный upstream default.

Файл: `app/tg_proxy_engine/raw_websocket.py`.  
Тесты: `tests/test_tg_websocket_frames.py`.

### 3. ZIP bomb/resource exhaustion в zapret updater — High

**Проблема:** проверялся SHA-256 архива, но не ограничивались размер download, число entries, размер отдельного файла и суммарный unpacked size. Подписанный, ошибочный или скомпрометированный upstream archive мог исчерпать RAM/disk.

**Исправлено:**
- download ≤ 100 MiB;
- ≤ 4096 entries;
- unpacked total ≤ 256 MiB;
- member ≤ 64 MiB;
- запрет encrypted entries и symlink entries;
- до остановки процессов проверяется наличие полного core bundle: `winws.exe`, WinDivert DLL/driver и хотя бы одной BAT-стратегии.

Файл: `app/updater.py`.  
Тест: `tests/test_updater_integrity.py`.

### 4. Ложный успех при сбое rebuild каталога стратегий — Medium

**Проблема:** исключение в `strategy_catalog.rebuild_from_bats()` только логировалось; версия всё равно отмечалась установленной.

**Исправлено:** версия больше не помечается установленной, пользователю возвращается retryable error.

### 5. Сборка могла навсегда закрепить устаревший vendor bundle — High

**Проблема:** `fetch_zapret.ps1` полностью пропускал проверку/загрузку, если существовал только `vendor/zapret/bin/winws.exe`. Неполный или старый набор DLL/driver/templates/lists молча попадал в новый installer.

**Исправлено:** build fetch теперь всегда определяет latest release, проверяет GitHub SHA-256, собирает bundle в staging, требует `winws.exe`, WinDivert DLL/driver и BAT-стратегии, записывает provenance marker и только затем полностью заменяет vendor directory.

Файл: `fetch_zapret.ps1`.

### 6. Самообновление приложения не ограничивало размер EXE — High

**Проблема:** установщик проверялся по SHA-256 перед запуском с правами администратора, но CDN мог отдать неограниченный поток и заполнить системный диск. Также не проверялось точное совпадение фактического размера с `asset.size` GitHub Release.

**Исправлено:** лимит загрузки 512 MiB проверяется по GitHub metadata, `Content-Length` и фактически прочитанным байтам; усечённый/разросшийся файл удаляется и никогда не запускается.

Файл: `app/self_updater.py`.  
Тесты: `tests/test_self_updater.py`.

### 7. Белый текст на белых карточках светлой темы — Medium

**Проблема:** подписи «Автоподбор» и «Тест обхода» — отдельные дочерние `QLabel`, поэтому не наследовали цвет `QPushButton` и оставались белыми на светлой карточке. Декоративные иконки также не скрывались в нейтральных темах вопреки логике темы.

**Исправлено:** заголовки и подзаголовки получают контрастную палитру активной темы; декоративные иконки скрываются в Light/Dark. Добавлен offline renderer контактного листа и regression test.

Файлы: `ui/theme_apply.py`, `tools/render_gui_audit.py`, `tests/test_gui_smoke.py`.

### 8. Невоспроизводимые release-build зависимости — Medium

**Проблема:** `build.bat` обновлял pip, устанавливал runtime-диапазоны и `pyinstaller>=6.0`, поэтому две сборки могли получить разные toolchain/dependencies без изменения репозитория.

**Исправлено:** release build использует отдельный список точно закреплённых top-level пакетов и PyInstaller; автоматическое обновление pip удалено. CI проверяет заявленный минимум Python 3.10 и release-интерпретатор 3.14.

Файлы: `requirements-build.txt`, `build.bat`, `.github/workflows/tests.yml`, `.github/workflows/release.yml`.

### 9. Предупреждения и проверка installer pipeline — Low

**Проблема:** Inno Setup 6.7 предупреждал об устаревшем architecture id `x64` и об отсутствии `RunOnceId` у удаления задачи автозапуска.

**Исправлено:** используется `x64compatible`, uninstall-команде назначен стабильный `RunOnceId`. Финальный PyInstaller clean-build версии 1.9.5 успешно создал `dist/ZapretGUI.exe` (54 789 314 bytes, SHA-256 `52ce218520f36ba2c0fd1c9362d1aa05801039e3760591860c1d55428fb9edea`). Inno Setup 6.7.3 собрал installer с явным `/DMyAppVersion=1.9.5` без предупреждений: `Output/ZapretGUI-Setup.exe` (56 273 697 bytes, SHA-256 `9b199630b4aff8d4e5d554dc2ae91f578a1e87d6e698d1bac906934ee35499e0`). PyInstaller отдельно предупреждает только о kernel dependencies WinDivert64.sys (`fwpkclnt.sys`, `WDFLDR.SYS`, `NDIS.SYS`), которые предоставляет Windows и не должны встраиваться в приложение.

Полный запуск нового EXE не выполнялся: на ПК уже запущена установленная копия из `C:\\Program Files\\ZapretGUI`, и single-instance guard корректно завершает вторую копию. Останавливать рабочее приложение без явного разрешения нельзя.

Файлы: `installer.iss`, `tools/smoke_built_exe.py`.

### 10. Уязвимая версия cryptography в release pins — High

**Проблема:** OSV обнаружил CVE-2026-69247 / GHSA-g6cj-pr64-35w5 в `cryptography==49.0.0`: различимые ошибки/timing в PKCS#7 EnvelopedData decryption могут образовать Bleichenbacher oracle. Проект напрямую не вызывает уязвимые PKCS#7 API, поэтому практическая экспозиция низкая, но уязвимая библиотека попадала в release EXE.

**Исправлено:** runtime range и release pin подняты до `cryptography==50.0.0`, где advisory исправлен. Повторный OSV query для 50.0.0 вернул пустой список; весь pytest и lint прошли на новой версии. Добавлен бесплатный OSV scan фактически установленных direct runtime dependencies, запускаемый в CI на каждом push/PR.

Файлы: `requirements.txt`, `requirements-build.txt`, `tools/check_vulnerabilities.py`, `.github/workflows/tests.yml`.

## Ещё требуется

1. Добавить безопасное удаление obsolete upstream-файлов при runtime-обновлении zapret. Пофайловый rollback уже восстанавливает все затронутые файлы, но неизвестные старые файлы намеренно не удаляются без manifest, чтобы не стереть пользовательские данные.
2. Получить криптографически проверяемый manifest для исходников tg-ws-proxy. GitHub публикует SHA-256 готовых EXE, но не zipball; текущая защита опирается на HTTPS/GitHub, staging, compile-check и строгую структурную проверку.
3. Поэтапно перенести оставшиеся совместимые изменения v1.7.3→v1.10.2 в bundled engine с сохранением локальных 429 cooldown, TLS verification и диагностики. Runtime updater уже ставит полный актуальный набор атомарно; слепо заменять bundled файлы небезопасно из-за upstream `CERT_NONE`.
4. Провести физический GUI smoke на DPI 100/125/150/200/250% и нескольких мониторах. Offline-render всех пяти вкладок и Light/Purple выполнен, найденный Light contrast bug исправлен, но виртуальный renderer не заменяет проверку реального Windows DPI.
5. Для полной воспроизводимости дополнить top-level pins transitive lock-файлом с hashes. Текущая сборка уже исключает плавающие top-level версии и автообновление pip; direct runtime dependencies автоматически проверяются через OSV в CI.
6. Выполнить контролируемый install/update/uninstall smoke в отдельной Windows VM. На текущем ПК installer намеренно не запускался: он закрывает все `ZapretGUI.exe`, а у пользователя работает установленная копия.

## Изменённые файлы

- `AUDIT_PLAN_PROMPT.md`
- `AUDIT_REPORT.md`
- `.github/workflows/tests.yml`
- `.github/workflows/release.yml`
- `CHANGELOG.md`
- `VERSION`
- `app/self_updater.py`
- `app/updater.py`
- `app/tg_proxy.py`
- `app/tg_proxy_engine/raw_websocket.py`
- `build.bat`
- `fetch_zapret.ps1`
- `installer.iss`
- `requirements.txt`
- `requirements-build.txt`
- `ui/theme_apply.py`
- `tests/test_gui_smoke.py`
- `tests/test_self_updater.py`
- `tests/test_tg_proxy_logic.py`
- `tests/test_tg_websocket_frames.py`
- `tests/test_updater_integrity.py`
- `tools/check_vulnerabilities.py`
- `tools/render_gui_audit.py`
- `tools/smoke_built_exe.py`
