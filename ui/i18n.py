"""UI string translations (Russian source -> English) and helpers.

Moved out of main_window.py: the tables are long, never change at
runtime, and both the window and the popup widgets need them.
"""
from __future__ import annotations

import re


_TRANSLATIONS = {
    "en": {
        "Главная": "Home",
        "Настройки": "Settings",
        "Стратегия": "Strategy",
        "Игры и сервисы": "Games & Services",
        "Автоподбор": "Auto-select",
        "Тест обхода": "Bypass test",
        "Отменить подбор": "Cancel auto-select",
        "Запущенная стратегия:": "Running strategy:",
        "отключено": "disabled",
        "подключено": "connected",
        "Запускать вместе с Windows": "Launch with Windows",
        "Запускать свёрнутым в трей": "Start minimized to tray",
        "Сворачивать в трей при закрытии": "Minimize to tray on close",
        "Проверять обновления стратегий при запуске": "Check strategy updates on launch",
        "Автоматически обновлять списки/IPset": "Auto-update lists/IPset",
        "Включать обход при запуске приложения": "Auto-start bypass on app launch",
        "ТЕМЫ:": "THEMES:",
        "Фиолетовая": "Purple",
        "Светлая": "Light",
        "Тёмная": "Dark",
        "Обновить приложение": "Update application",
        "Обновить zapret": "Update zapret",
        "Обновить списки/IPset": "Update lists/IPset",
        "HOSTS для Windows": "Windows HOSTS",
        "Список": "List",
        "Редактор": "Editor",
        "Логи": "Logs",
        "Стратегия:": "Strategy:",
        "Доступные стратегии:": "Available strategies:",
        "Обновить список": "Refresh list",
        "Запустить выбранную": "Run selected",
        "Своя стратегия (аргументы winws.exe)": "Custom strategy (winws.exe arguments)",
        "Название стратегии": "Strategy name",
        "Проверить": "Validate",
        "Сохранить": "Save",
        "Удалить": "Delete",
        "Списки доменов / ipset": "Domain / ipset lists",
        "Сохранить список": "Save list",
        "Копировать": "Copy",
        "Очистить": "Clear",
        "Применять обход": "Apply bypass",
        "НЕ Применять обход": "Do NOT apply bypass",
        "Свои домены (через запятую)": "Custom domains (comma-separated)",
        "Изменения сохраняются сразу. Если zapret включён — он перезапустится автоматически.": "Changes are saved instantly. If zapret is enabled, it will restart automatically.",
        "Игровой фильтр (эксперимент)": "Game filter (experimental)",
        "Применять обход к игровому трафику (порты 1024-65535)": "Apply bypass to game traffic (ports 1024-65535)",
        "Применяет DPI-обход к игровому UDP/TCP на высоких портах. Иногда помогает (если сервис режется по DPI), но ЧАЩЕ ломает игры — в РФ они обычно не блокируются по DPI. Включай для теста; стало хуже — выключи.": "Applies DPI bypass to game UDP/TCP on high ports. Sometimes helps if a service is DPI-filtered, but MORE OFTEN breaks games — in Russia they usually are not DPI-blocked. Enable for testing; if it gets worse, turn it off.",
        "Zapret всё ещё работает": "Zapret is still running",
        "Оставить приложение в трее или полностью выключить обход?": "Keep the app in tray or fully stop the bypass?",
        "В трей": "To tray",
        "Выключить": "Turn off",
        "Приложение свёрнуто в трей.": "The app was minimized to tray.",
        "Работает!": "Works!",
        "Не работает": "Not working",
        "Ищу лучшую\nстратегию для вас!": "Looking for the best\nstrategy for you!",
        "Отмена": "Cancel",
        "Подготовка...": "Preparing...",
        "Подбор отменён.": "Auto-select cancelled.",
        "Проверка...": "Checking...",
        "Подготовка zapret": "Preparing zapret",
        "Загружаем необходимые файлы...": "Downloading required files...",
        "Файлы zapret ещё не готовы. Идёт подготовка, попробуйте через несколько секунд.": "Zapret files are not ready yet. Preparation is in progress; try again in a few seconds.",
        "Не удалось подготовить zapret": "Could not prepare zapret",
        "Проверьте интернет-соединение и попробуйте снова.\n\n": "Check your internet connection and try again.\n\n",
        "Рабочая стратегия не найдена.": "No working strategy found.",
        "Файлы zapret готовы.": "Zapret files are ready.",
        "Обновление zapret...": "Updating zapret...",
        "Служба автозапуска: ": "Autostart service: ",
        "Служба: ": "Service: ",
        "остановлен": "stopped",
        "работает": "running",
        "Статус: ": "Status: ",
        "Остановить": "Stop",
        "Запустить": "Start",
        "Открыть окно": "Open window",
        "Выход": "Exit",
        "быстрый отбор": "quick selection",
        "успех": "success",
        "Отмена...": "Cancelling...",
        "Нет выбранной стратегии.": "No strategy selected.",
        "Ошибка запуска": "Launch error",
        "Стратегии не найдены": "No strategies found",
        "Не удалось найти доступные стратегии для автоподбора.": "Could not find available strategies for auto-selection.",
        "Стратегия найдена": "Strategy found",
        "Стратегия не найдена": "Strategy not found",
        "Ни одна стратегия не разблокировала доступ.\nПопробуйте обновить списки доменов и убедитесь, что приложение запущено от имени администратора.": "No strategy unlocked access.\nTry updating the domain lists and make sure the app is running as administrator.",
        "Укажите название и аргументы.": "Enter a name and arguments.",
        "Стратегия сохранена.": "Strategy saved.",
        "Удалено.": "Deleted.",
        "Нет такой пользовательской стратегии.": "No such custom strategy.",
        "Список сохранён.": "List saved.",
        "Обновление": "Update",
        "Проверка": "Validation",
        "Доступна новая версия": "New version available",
        # --- Telegram proxy tab ---
        "Telegram": "Telegram",
        "Telegram прокси": "Telegram proxy",
        "Локальный MTProto-прокси для Telegram Desktop. Telegram подключается к нему, а прокси туннелирует трафик через WebSocket к серверам Telegram — обход блокировок без сторонних серверов.":
            "Local MTProto proxy for Telegram Desktop. Telegram connects to it and the proxy tunnels traffic via WebSocket to Telegram servers — bypassing blocks without any third-party server.",
        "Запускать вместе с zapret": "Start together with zapret",
        "Прокси выключен": "Proxy is off",
        "Прокси запущен": "Proxy is running",
        "Запуск прокси...": "Starting proxy...",
        "Остановить прокси": "Stop proxy",
        "Запустить прокси": "Start proxy",
        "Скопировать ссылку": "Copy link",
        "Открыть в Telegram": "Open in Telegram",
        "Ссылка для подключения": "Connection link",
        "Сервер": "Server",
        "Порт": "Port",
        "Secret": "Secret",
        "Секрет появится после первого запуска прокси.":
            "The secret appears after the proxy's first launch.",
        "Подготовка Telegram прокси": "Preparing Telegram proxy",
        "Загрузка tg-ws-proxy...": "Downloading tg-ws-proxy...",
        "Не удалось подготовить Telegram прокси": "Could not prepare Telegram proxy",
        "Ссылка скопирована в буфер обмена.": "Link copied to clipboard.",
        "Ссылка ещё не готова — запустите прокси.": "Link is not ready yet — start the proxy first.",
        "Telegram прокси остановился": "Telegram proxy stopped",
        "Обновить tg-ws-proxy": "Update tg-ws-proxy",
        "Проверить обновления tg-ws-proxy": "Check for tg-ws-proxy updates",
        "Сгенерировать новый secret": "Generate new secret",
        "Проверяю...": "Checking...",
        # --- Telegram proxy tab: DC IP overrides (advanced) ---
        "Дополнительно: DC IP-адреса": "Advanced: DC IP addresses",
        "Дополнительно: Cloudflare fallback": "Advanced: Cloudflare fallback",
        "Список «DC:IP» через запятую. По умолчанию используются встроенные адреса (2:149.154.167.220, 4:149.154.167.220). Заполняйте только если Telegram сменил адреса дата-центров: новые значения применятся при следующем запуске прокси.":
            "Comma-separated list of \"DC:IP\" entries. Defaults to the built-in addresses (2:149.154.167.220, 4:149.154.167.220). Fill in only if Telegram rotates its datacenter addresses — new values take effect on the next proxy start.",
    }
}
_TRANSLATIONS_REVERSE = {v: k for k, v in _TRANSLATIONS["en"].items()}


def tr_text(lang: str, text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    if lang == "en":
        return _TRANSLATIONS["en"].get(text, text)
    return _TRANSLATIONS_REVERSE.get(text, text)



def localize_runtime_text(lang: str, text: str) -> str:
    """Translate dynamic status/log/update strings for the English UI."""
    if lang != "en" or not isinstance(text, str):
        return text
    out = text
    replacements = {
        "[обновление]": "[update]",
        "[запуск]": "[launch]",
        "[Запуск]": "[Launch]",
        "[Команда]": "[Command]",
        "[проверка]": "[check]",
        "[Проверка]": "[Check]",
        "[служба]": "[service]",
        "у вас последняя версия.": "you have the latest version.",
        "Загрузка ": "Downloading ",
        "Ошибка загрузки: ": "Download error: ",
        "Ошибка распаковки: ": "Extraction error: ",
        "Модуль requests не установлен.": "The requests module is not installed.",
        "У релиза нет zip-архива.": "The release has no zip archive.",
        "Скачанный архив повреждён, попробуйте ещё раз.": "The downloaded archive is corrupted, please try again.",
        "Пропущен занятый файл: ": "Skipped busy file: ",
        "# ошибка: ": "# error: ",
        "Аргументы пусты.": "Arguments are empty.",
        "Непарные кавычки.": "Unmatched quotes.",
        "Нет ни --wf-tcp/--wf-udp, ни --dpi-desync — стратегия скорее всего не заработает.": "No --wf-tcp/--wf-udp or --dpi-desync — the strategy will probably not work.",
    }
    for ru, en in replacements.items():
        out = out.replace(ru, en)
    out = re.sub(r"Доступна новая версия ([^.]+)\. Скачать и обновить стратегии\?", r"New version \1 is available. Download and update strategies?", out)
    out = re.sub(r"Обновлено до ([^:]+): распаковано (\d+) файлов\.", r"Updated to \1: unpacked \2 files.", out)
    out = re.sub(r"Пропущено (\d+) занятых файлов \(остановите защиту и повторите\)\.", r"Skipped \1 busy files (stop protection and try again).", out)
    out = re.sub(r", отклик ~([0-9]+) мс", r", latency ~\1 ms", out)
    out = out.replace("Лучшая стратегия", "Best strategy")
    out = out.replace("Рабочая стратегия", "Working strategy")
    out = out.replace("Частично рабочая", "Partially working")
    out = out.replace("стратегия включена", "strategy enabled")
    return out
