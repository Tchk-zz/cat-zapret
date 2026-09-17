# Release checklist

Релиз публикуется только через `.github/workflows/release.yml`. Локальная сборка
может использоваться для диагностики, но официальным считается installer,
созданный GitHub Actions из release tag.

## 1. Подготовка

- [ ] Рабочее дерево чистое и `main` синхронизирован с `origin/main`.
- [ ] В `VERSION` записан следующий SemVer без `v` (например, `1.9.7`).
- [ ] Вверху `CHANGELOG.md` есть секция с той же версией и датой.
- [ ] Документация и заметки миграции отражают пользовательские изменения.
- [ ] Проверены лицензии изменённых зависимостей и upstream-компонентов.
- [ ] В репозитории нет EXE, ZIP, журналов, кэшей, секретов и персональных данных.

## 2. Зависимости

- [ ] Runtime-диапазоны в `requirements.txt` совместимы с Python 3.10 и 3.14.
- [ ] Top-level release pins в `requirements-build.txt` обновлены осознанно.
- [ ] Для каждого нового pin просмотрены changelog и license metadata.
- [ ] `python tools/check_vulnerabilities.py` не находит известных проблем.

Не обновляйте версии во время самой сборки: одинаковый commit должен давать один
и тот же набор top-level зависимостей.

## 3. Quality gates

В чистой virtual environment:

```powershell
python tools/check_lint.py
python tools/check_vulnerabilities.py
python -m pytest tests/ -q --no-header
python -m compileall -q app ui tools
```

Дополнительно:

- [ ] `python tools/render_gui_audit.py` — визуально проверены Light, Purple и все вкладки.
- [ ] `git diff --check` не показывает пробелы или конфликты.
- [ ] Проверены `VERSION`, package version и Inno version contract.
- [ ] При изменении updater выполнены тесты обычного пути, пути с пробелами,
      checksum mismatch, truncated или oversized download и rollback.

## 4. Commit и tag

```powershell
git add -A
git commit -m "release: 1.9.7"
git push origin main
git tag -a v1.9.7 -m "Zapret GUI 1.9.7"
git push origin v1.9.7
```

Tag обязан совпадать с `v` плюс содержимое `VERSION`. Push tag запускает release
workflow, который повторно выполняет lint, OSV и tests, получает проверенный
Zapret bundle, собирает PyInstaller EXE и Inno Setup installer, а затем
публикует Release.

## 5. Проверка GitHub Actions

- [ ] Tests workflow на `main` зелёный для Python 3.10 и 3.14.
- [ ] Release workflow завершился без warning об устаревшем Node runtime.
- [ ] Артефакт `ZapretGUI-Setup-<version>` доступен.
- [ ] В Release ровно актуальный `ZapretGUI-Setup.exe`.
- [ ] Release notes взяты из правильной секции CHANGELOG.
- [ ] В notes опубликован SHA-256; независимо вычисленный hash совпадает.

## 6. Smoke test

В отдельной Windows VM или контролируемой тестовой установке:

- [ ] чистая установка;
- [ ] запуск с UAC и отображение версии;
- [ ] запуск и остановка Zapret, тест обхода;
- [ ] полное обновление bundle с HOSTS, IPSet, lists и `.service`;
- [ ] сохранение user lists, config и custom strategies;
- [ ] Telegram proxy start, update и stop;
- [ ] обновление приложения из предыдущей исправной версии;
- [ ] uninstall без удаления пользовательских данных вне каталога приложения.

### Миграция 1.9.5/1.9.6 → 1.9.7

Старый updater может не запустить скачанный EXE из-за двойного quoting. Для этого
перехода обязательно укажите в Release notes: при ошибке поиска временного файла
нужно один раз скачать 1.9.7 вручную. После установки 1.9.7 последующие обновления
проверяются тем же набором regression-тестов.

## 7. После публикации

- [ ] Latest Release открывается и download не возвращает 404.
- [ ] README badges и ссылка Latest отображают новую версию.
- [ ] GitHub repository metadata и topics актуальны.
- [ ] Issue tracker проверен на регрессии первых установок.

Если workflow упал до публикации, исправьте причину и перезапустите его: publish
script обновляет существующий Release и asset идемпотентно. Не создавайте второй
tag с тем же номером и не загружайте непроверенный локальный installer вручную.
