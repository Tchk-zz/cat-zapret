# Zapret GUI

Удобный графический интерфейс для [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) (автор движка — Flowseal). Приложение не заменяет zapret, а управляет им: запускает `winws.exe` с нужными аргументами, автоматически подбирает рабочую стратегию и следит за состоянием.

## Возможности

- **Автоподбор рабочей стратегии** — последовательный перебор стратегий с реальной проверкой доступа к Discord и YouTube.
- **Большой выбор стратегий** — список строится автоматически из `.bat`-файлов zapret.
- **Служба Windows** — установка / удаление.
- **Автозапуск с Windows** + запуск свёрнутым в трей.
- **Трей с индикатором состояния** (зелёный / красный / жёлтый).
- **Обновление стратегий из репозитория** Flowseal (с сохранением пользовательских стратегий).
- **Редактор** своих стратегий и списков доменов / ipset.

## Размещение

Положите папку `zapret-gui` **рядом** с распакованным zapret-discord-youtube:

```
...\
  zapret-discord-youtube\   <- здесь bin\winws.exe, *.bat, lists\
  zapret-gui\               <- это приложение
```

Папка zapret определяется автоматически (ищется `bin\winws.exe`). Если не нашлась — укажите её во вкладке «Настройки».

## Запуск из исходников

Требуется Python 3.10+ и Windows 10/11.

```bat
pip install -r requirements.txt
python main.py
```

Приложению нужны права администратора (драйвер WinDivert). При запуске оно само запросит UAC.

## Сборка .exe

```bat
build.bat
```

или вручную:

```bat
pip install pyinstaller
pyinstaller zapret-gui.spec --noconfirm
```

Результат — `dist\ZapretGUI.exe` (один файл, без консоли, с запросом админа).

## Как работает автоподбор

1. Берёт стратегии в порядке приоритета.
2. Запускает `winws.exe` с очередной стратегией, ждёт прогрев.
3. Проверяет реальный доступ к YouTube и Discord (HTTPS-запросы).
4. Первая стратегия, где оба сервиса доступны, фиксируется и запоминается.

## Решение проблем

- **Антивирус ругается на winws.exe / WinDivert** — это ложное срабатывание; добавьте папку zapret в исключения.
- **Ошибка запуска / служба конфликтует** — остановите службу zapret или другой запущенный winws.exe (приложение делает это автоматически перед стартом).
- **Нет стратегий в списке** — проверьте, что указана правильная папка zapret с `.bat`-файлами.
- **Нет доступа после подбора** — обновите стратегии (провайдеры меняют блокировки).

## Структура проекта

```
zapret-gui/
  main.py                 — точка входа, UAC/админ
  requirements.txt
  build.bat / zapret-gui.spec
  app/
    config.py             — настройки + автопоиск папки zapret
    strategy_manager.py   — разбор .bat в стратегии
    process_runner.py     — запуск/остановка winws.exe
    connectivity.py       — проверка доступа YouTube/Discord
    auto_selector.py      — логика автоподбора
    service_manager.py    — служба Windows
    autostart.py          — автозапуск
    updater.py            — обновление стратегий с GitHub
    editor.py             — валидация редактора
  ui/
    main_window.py        — главное окно (вкладки)
    tray.py               — иконка в трее
    workers.py            — фоновые потоки
    theme.py              — тёмная тема
```

## Лицензия и благодарности

Движок zapret и стратегии — собственность [Flowseal](https://github.com/Flowseal/zapret-discord-youtube) и авторов zapret. Этот GUI — независимая оболочка.

## Публикация на GitHub и лицензия

Этот проект — независимый GUI/оболочка для zapret-discord-youtube. Он не является официальным проектом Flowseal, bol-van, Discord или YouTube.

Рекомендуемая лицензия репозитория: **GPL-3.0**. Причина: интерфейс написан на PyQt6, а PyQt6 распространяется под GPL-3.0 или коммерческой лицензией Riverbank. Если вы хотите использовать MIT/закрытую лицензию для GUI, сначала нужно купить коммерческую лицензию PyQt или перейти на другой GUI-фреймворк и заново проверить лицензии.

В репозиторий не следует коммитить скачанный `vendor/zapret/bin`, `dist`, `build`, личные настройки и логи. Сборочный скрипт сам скачивает официальный Flowseal-релиз при сборке.

### Благодарности и зависимости

- Flowseal/zapret-discord-youtube: https://github.com/Flowseal/zapret-discord-youtube
- bol-van/zapret: https://github.com/bol-van/zapret
- WinDivert: https://github.com/basil00/WinDivert
- PyQt6: https://pypi.org/project/PyQt6/

Подробности см. в `NOTICE` и `THIRD_PARTY_NOTICES.md`.
