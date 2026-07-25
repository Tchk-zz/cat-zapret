"""SettingsTabMixin — part of MainWindow, kept in its own file.

These methods were moved out of ui/main_window.py unchanged. They are
mixed into MainWindow, so ``self`` still refers to the window and every
attribute they use lives there as before.
"""
from __future__ import annotations


from PyQt6.QtCore import (
    Qt,
)
from PyQt6.QtGui import (
    QColor, QPixmap,
)
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from app import autostart
from .paths import asset_path
from .i18n import (  # noqa: E402
    _TRANSLATIONS,
    _TRANSLATIONS_REVERSE,
    localize_runtime_text,
    tr_text,
)
from .widgets_custom import (  # noqa: E402
    POPUP_DARK_QSS,
    POPUP_LIGHT_QSS,
    POPUP_QSS,
    AnimatedGradientProgressBar,
    AutoSelectProgressPopup,
    BypassTestPopup,
    GamesColumnIcon,
    PowerButton,
    StyledPopup,
    _Dark3DButton,
    _Dark3DPanel,
    _DarkAnimatedProgressBar,
    _GlassNav,
    _HomeAutoSelectPanel,
    _paint_dark_3d_surface,
    _SettingsRow,
    _ShimmerPlate,
    _SleepZWidget,
)


class SettingsTabMixin:
    """Mixin: see module docstring."""

    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("settingsRoot")
        lay = QVBoxLayout(w)
        # Reduced top margin (was 78) so the settings card + all checkboxes
        # + theme selector + buttons fit within the 800px window height
        # without triggering a scrollbar.
        lay.setContentsMargins(42, 24, 42, 16)
        lay.setSpacing(0)
        self.settings_root_layout = lay

        card = QFrame()
        self.settings_card = card
        card.setObjectName("settingsCard")
        card_shadow = QGraphicsDropShadowEffect(card)
        card_shadow.setBlurRadius(34)
        card_shadow.setOffset(0, 8)
        card_shadow.setColor(QColor(0, 0, 0, 95))
        card.setGraphicsEffect(card_shadow)
        card_lay = QVBoxLayout(card)
        # Reduced card margins (was 54/28/54/30) to save vertical space.
        card_lay.setContentsMargins(48, 18, 48, 18)
        card_lay.setSpacing(8)
        self.settings_card_layout = card_lay
        self.settings_rows = []

        # Keep the path field available for the existing browse logic, but the
        # redesigned Settings screen follows the mockup and no longer shows the
        # technical zapret-folder row.
        self.dir_edit = QLineEdit(str(self.zapret_dir))
        self.dir_edit.setReadOnly(True)
        self.dir_edit.hide()

        lang_row = QHBoxLayout()
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_row.addStretch(1)
        self.btn_lang = QPushButton()
        self.btn_lang.setObjectName("settingsLangBtn")
        self.btn_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lang.clicked.connect(self._toggle_language)
        lang_row.addWidget(self.btn_lang)
        card_lay.addLayout(lang_row)

        settings_rows_layout = QVBoxLayout()
        settings_rows_layout.setContentsMargins(0, 0, 0, 0)
        settings_rows_layout.setSpacing(8)
        self.settings_rows_layout = settings_rows_layout
        card_lay.addLayout(settings_rows_layout)

        cat = QLabel()
        self.settings_cat = cat
        cat.setObjectName("settingsCat")
        cat_pm = QPixmap(asset_path("settings_cat.png"))
        if not cat_pm.isNull():
            cat.setPixmap(cat_pm.scaled(
                180, 90,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        cat.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        # Reduced from 138 to 92 to save vertical space.
        cat.setFixedHeight(92)
        lay.addWidget(cat, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(-16)

        def add_setting_row(cb: QCheckBox) -> None:
            row = _SettingsRow(cb)
            row.setObjectName("settingsRow")
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            row_lay = QHBoxLayout(row)
            # Reduced vertical margins (was 7/7) to save space.
            row_lay.setContentsMargins(18, 5, 18, 5)
            row_lay.setSpacing(8)
            row_lay.addWidget(cb)
            settings_rows_layout.addWidget(row)
            self.settings_rows.append((row, row_lay, cb))

        self.cb_autostart = QCheckBox("\u0417\u0430\u043f\u0443\u0441\u043a\u0430\u0442\u044c \u0432\u043c\u0435\u0441\u0442\u0435 \u0441 Windows")
        self.cb_autostart.setObjectName("settingsCheck")
        self.cb_autostart.setChecked(autostart.is_enabled())
        self.cb_autostart.toggled.connect(self._toggle_autostart)
        add_setting_row(self.cb_autostart)

        self.cb_minimized = QCheckBox("\u0417\u0430\u043f\u0443\u0441\u043a\u0430\u0442\u044c \u0441\u0432\u0451\u0440\u043d\u0443\u0442\u044b\u043c \u0432 \u0442\u0440\u0435\u0439")
        self.cb_minimized.setObjectName("settingsCheck")
        self.cb_minimized.setChecked(self.config.start_minimized)
        self.cb_minimized.toggled.connect(self._toggle_minimized)
        add_setting_row(self.cb_minimized)

        self.cb_autostart_strategy = QCheckBox("\u0412\u043a\u043b\u044e\u0447\u0430\u0442\u044c \u043e\u0431\u0445\u043e\u0434 \u043f\u0440\u0438 \u0437\u0430\u043f\u0443\u0441\u043a\u0435 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f")
        self.cb_autostart_strategy.setObjectName("settingsCheck")
        self.cb_autostart_strategy.setChecked(bool(getattr(self.config, "autostart_strategy", False)))
        self.cb_autostart_strategy.setToolTip(
            "При запуске ZapretGUI автоматически включит последнюю рабочую стратегию.\n"
            "Если стоит галочка «Запускать вместе с zapret» на вкладке Telegram —\n"
            "Telegram-прокси тоже включится автоматически."
        )
        self.cb_autostart_strategy.toggled.connect(self._toggle_autostart_strategy)
        add_setting_row(self.cb_autostart_strategy)

        self.cb_tray = QCheckBox("\u0421\u0432\u043e\u0440\u0430\u0447\u0438\u0432\u0430\u0442\u044c \u0432 \u0442\u0440\u0435\u0439 \u043f\u0440\u0438 \u0437\u0430\u043a\u0440\u044b\u0442\u0438\u0438")
        self.cb_tray.setObjectName("settingsCheck")
        self.cb_tray.setChecked(self.config.minimize_to_tray)
        self.cb_tray.toggled.connect(self._toggle_tray)
        add_setting_row(self.cb_tray)

        self.cb_updates = QCheckBox("\u041f\u0440\u043e\u0432\u0435\u0440\u044f\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0439 \u043f\u0440\u0438 \u0437\u0430\u043f\u0443\u0441\u043a\u0435")
        self.cb_updates.setObjectName("settingsCheck")
        self.cb_updates.setChecked(self.config.check_updates_on_launch)
        self.cb_updates.toggled.connect(self._toggle_updates)
        add_setting_row(self.cb_updates)

        self.cb_auto_lists = QCheckBox("Автоматически обновлять списки/IPset")
        self.cb_auto_lists.setObjectName("settingsCheck")
        self.cb_auto_lists.setChecked(bool(getattr(self.config, "auto_update_lists", True)))
        self.cb_auto_lists.setToolTip(
            "Раз в 24 часа обновляет upstream list/ipset/hosts-template файлы zapret. "
            "Пользовательские *-user.txt не трогаются."
        )
        self.cb_auto_lists.toggled.connect(self._toggle_auto_update_lists)
        add_setting_row(self.cb_auto_lists)

        self.settings_theme_gap = QWidget()
        self.settings_theme_gap.setFixedHeight(30)
        card_lay.addWidget(self.settings_theme_gap)

        theme_title = QLabel("\u0422\u0415\u041c\u042b:")
        theme_title.setObjectName("settingsThemeTitle")
        theme_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.settings_theme_title = theme_title
        card_lay.addWidget(theme_title)

        self.settings_theme_selector_gap = QWidget()
        self.settings_theme_selector_gap.setFixedHeight(20)
        card_lay.addWidget(self.settings_theme_selector_gap)

        # Theme selector: a single button that opens a dropdown menu listing
        # all available themes (3 presets + 7 image themes). Replaces the old
        # 3-checkbox row.
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(8)
        theme_row.addStretch(1)
        self.btn_theme_select = QPushButton(self._current_theme_display_name())
        self.btn_theme_select.setObjectName("secondaryBtn")
        self.btn_theme_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_select.setToolTip(
            "Нажмите, чтобы выбрать тему оформления.\n"
            "Доступно 10 тем: 3 классические + 7 с фоновыми изображениями."
        )
        self.btn_theme_select.clicked.connect(self._show_theme_menu)
        theme_row.addWidget(self.btn_theme_select)
        theme_row.addStretch(1)
        card_lay.addLayout(theme_row)

        self.settings_updates_gap = QWidget()
        self.settings_updates_gap.setFixedHeight(30)
        card_lay.addWidget(self.settings_updates_gap)
        settings_updates_layout = QVBoxLayout()
        settings_updates_layout.setContentsMargins(0, 0, 0, 0)
        settings_updates_layout.setSpacing(8)
        self.settings_updates_layout = settings_updates_layout
        card_lay.addLayout(settings_updates_layout)

        btn_update = QPushButton("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435")
        btn_update.setObjectName("settingsSoftBtn")
        # Reserved for future app patch/update flow. Intentionally clickable,
        # but currently has no action attached.
        settings_updates_layout.addWidget(btn_update)
        btn_force_update = QPushButton("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c zapret")
        btn_force_update.setObjectName("settingsPrimaryBtn")
        btn_force_update.setToolTip(
            "\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u044e\u044e \u0432\u0435\u0440\u0441\u0438\u044e \u0441 GitHub, \u043f\u0435\u0440\u0435\u043f\u0438\u0441\u0430\u0442\u044c \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438 \u0438\u0437 \u043d\u043e\u0432\u044b\u0445 \u0431\u0430\u0442\u043d\u0438\u043a\u043e\u0432 \u0438 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0438\u0445."
        )
        btn_force_update.clicked.connect(self.force_update_zapret)
        settings_updates_layout.addWidget(btn_force_update)

        self.btn_update_lists = QPushButton("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043a\u0438/IPset")
        self.btn_update_lists.setObjectName("settingsPrimaryBtn")
        self.btn_update_lists.setToolTip(
            "Обновить только upstream list/ipset/hosts-template файлы zapret. "
            "Пользовательские списки и настройки не перезаписываются."
        )
        self.btn_update_lists.clicked.connect(self.force_update_lists)
        settings_updates_layout.addWidget(self.btn_update_lists)

        self.btn_hosts_dialog = QPushButton("HOSTS для Windows")
        self.btn_hosts_dialog.setObjectName("settingsSoftBtn")
        self.btn_hosts_dialog.setToolTip(
            "Показать строки для системного Windows HOSTS как в оригинальном Flowseal zapret. "
            "Автоматически HOSTS не меняется без подтверждения."
        )
        self.btn_hosts_dialog.clicked.connect(self.show_hosts_dialog)
        settings_updates_layout.addWidget(self.btn_hosts_dialog)

        lay.addWidget(card)
        lay.addStretch(1)
        return w
