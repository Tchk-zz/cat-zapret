"""HomeTabMixin — part of MainWindow, kept in its own file.

These methods were moved out of ui/main_window.py unchanged. They are
mixed into MainWindow, so ``self`` still refers to the window and every
attribute they use lives there as before.
"""
from __future__ import annotations


from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSize,
)
from PyQt6.QtGui import (
    QColor, QIcon, QPixmap,
)
from PyQt6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from app.config import default_data_dir
from app import tg_proxy
from .effects import apply_effect
from .paths import asset_path
from .waiting_runner_game import WaitingRunnerGame
from .widgets_custom import (  # noqa: E402
    PowerButton,
    _Dark3DButton,
    _Dark3DPanel,
    _HomeAutoSelectPanel,
    _SleepZWidget,
)


class HomeTabMixin:
    """Mixin: see module docstring."""

    def _build_home_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("homeRoot")
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # Home widgets are created once; the arrangement is rebuilt on demand
        # so the dark theme can use its own layout without duplicating widgets
        # (duplicating would break status/log/auto-select wiring). Purple and
        # light presets keep the original classic layout untouched.
        self._create_home_widgets(w)
        self.home_body = QWidget()
        self.home_body.setObjectName("homeBody")
        outer.addWidget(self.home_body)
        self._home_layout_built = False
        self._apply_home_layout()
        return w

    def _create_home_widgets(self, w: QWidget) -> None:
        # --- central ON/OFF power button ---
        self.btn_toggle = PowerButton()
        self.btn_toggle.setObjectName("powerBtn")
        self.btn_toggle.setProperty("running", "false")
        self.btn_toggle.setToolTip("Вкл/выкл — автоматически подбирает рабочую стратегию")
        self.btn_toggle.clicked.connect(self.power_toggle)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(150, 90, 240))
        self._glow.setBlurRadius(26)
        self._glow_installed = apply_effect(self.btn_toggle, self._glow)
        self._glow_anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._glow_anim.setDuration(1400)
        self._glow_anim.setStartValue(24)
        self._glow_anim.setKeyValueAt(0.5, 64)
        self._glow_anim.setEndValue(24)
        self._glow_anim.setLoopCount(-1)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_color_anim = QPropertyAnimation(self._glow, b"color", self)
        self._glow_color_anim.setDuration(2200)
        self._glow_color_anim.setKeyValueAt(0.0, QColor(38, 200, 120))
        self._glow_color_anim.setKeyValueAt(0.5, QColor(120, 255, 175))
        self._glow_color_anim.setKeyValueAt(1.0, QColor(38, 200, 120))
        self._glow_color_anim.setLoopCount(-1)
        self._glow_color_anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        # Cat mascot that peeks over the power button (dark theme only).
        self.home_cat = QLabel()
        self.home_cat.setObjectName("homeCat")
        self.home_cat.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.home_cat.setScaledContents(True)
        self.home_cat.setVisible(False)
        # The mascot frames are decoded on first use, not here: the classic
        # (purple/light/image) presets never show the cat, and the "searching"
        # frame only appears while auto-select runs. Loading all three up front
        # cost megabytes of RAM on every launch for nothing. See
        # _home_cat_frame_pixmap() / _set_home_cat_frame().
        self._home_cat_cache: dict[str, QPixmap] = {}
        self._home_cat_scaled_cache: dict[tuple[str, int, int], QPixmap] = {}
        self._home_cat_auto_active = False
        self.sleep_z = _SleepZWidget()
        # --- status pill ---
        self.status_pill = QFrame()
        self.status_pill.setObjectName("statusPill")
        _pill_shadow = QGraphicsDropShadowEffect(self.status_pill)
        _pill_shadow.setBlurRadius(24)
        _pill_shadow.setOffset(0, 2)
        _pill_shadow.setColor(QColor(0, 0, 0, 95))
        apply_effect(self.status_pill, _pill_shadow)
        pill = QHBoxLayout(self.status_pill)
        pill.setContentsMargins(14, 6, 18, 6)
        pill.setSpacing(4)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setStyleSheet("color: #ff5c6c; padding-top: 2px;")
        self.status_label = QLabel("отключено")
        self.status_label.setObjectName("statusText")
        pill.addWidget(self.status_dot)
        pill.addWidget(self.status_label)
        # --- action buttons ---
        self.btn_auto = _Dark3DButton("Автоподбор")
        self.btn_auto.setObjectName("gradBtn")
        self.btn_auto.setIcon(QIcon(asset_path("auto_select_icon_256.png")))
        self.btn_auto.setIconSize(QSize(50, 50))
        self.btn_auto.setToolTip("Подобрать лучшую стратегию из рабочих")
        self.btn_auto.clicked.connect(lambda: self.start_auto_select("best"))
        self.btn_check = _Dark3DButton("Тест обхода")
        self.btn_check.setObjectName("gradBtn")
        self.btn_check.setIcon(QIcon(asset_path("check_icon_256.png")))
        self.btn_check.setIconSize(QSize(50, 50))
        self.btn_check.setToolTip("Проверить доступ к YouTube и Discord")
        self.btn_check.clicked.connect(self.manual_check)
        self.btn_auto_cancel = QPushButton("Отменить подбор")
        self.btn_auto_cancel.setObjectName("ghostBtn")
        self.btn_auto_cancel.clicked.connect(self._cancel_auto_select)
        self.btn_auto_cancel.setVisible(False)
        # Hidden mode buttons kept so the auto-select logic stays intact.
        self.btn_auto_best = QPushButton("best", w)
        self.btn_auto_best.setVisible(False)
        self.btn_auto_best.clicked.connect(lambda: self.start_auto_select("best"))
        self.btn_auto_work = QPushButton("working", w)
        self.btn_auto_work.setVisible(False)
        self.btn_auto_work.clicked.connect(lambda: self.start_auto_select("working"))
        # Running strategy + log box (reused as the "Zapret" card in dark).
        self.run_box = QFrame()
        self.run_box.setObjectName("runBox")
        rb = QVBoxLayout(self.run_box)
        rb.setContentsMargins(16, 14, 16, 16)
        rb.setSpacing(10)
        self.run_title = QLabel("Запущенная стратегия:")
        self.run_title.setObjectName("runTitle")
        self.run_title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        rb.addWidget(self.run_title)
        self.run_field = QLineEdit("—")
        self.run_field.setObjectName("runField")
        self.run_field.setReadOnly(True)
        rb.addWidget(self.run_field)
        self.home_log = QTextEdit()
        self.home_log.setObjectName("homeLog")
        self.home_log.setReadOnly(True)
        self.home_log.setMinimumHeight(100)
        rb.addWidget(self.home_log, 1)
        # Progress + caption (auto-select / update feedback).
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("muted")
        self.progress_label.setWordWrap(True)
        # Hidden compatibility label for service status text.
        self.svc_inline = QLabel("", w)
        self.svc_inline.setObjectName("muted")
        self.svc_inline.setVisible(False)
        # Telegram summary card (dark theme only).
        self._create_home_tg_card()
        # Zapret status card (dark theme only).
        self._create_home_zapret_card()
        # Icon + title + description inside the dark action buttons.
        self._build_action_decorations()
        # Embedded autoselect progress panel + waiting mini-game (dark Home only).
        self.home_auto_panel = _HomeAutoSelectPanel(self)
        self.home_auto_panel.cancel_button.clicked.connect(self._cancel_auto_select)

        self.home_runner_card = _Dark3DPanel(self)
        self.home_runner_card.setObjectName("homeRunnerCard")
        self.home_runner_card.setStyleSheet(
            "QFrame#homeRunnerCard { background: transparent; border: none; }"
        )
        self.home_runner_card.setFixedHeight(390)
        runner_card_layout = QVBoxLayout(self.home_runner_card)
        runner_card_layout.setContentsMargins(3, 3, 3, 3)
        runner_card_layout.setSpacing(0)
        self.waiting_runner_game = WaitingRunnerGame(
            default_data_dir() / "waiting_runner_best.txt",
            self.home_runner_card,
        )
        self.waiting_runner_game.roundEnded.connect(self._on_waiting_runner_round_ended)
        runner_card_layout.addWidget(self.waiting_runner_game)

        self.home_auto_stack = QWidget(self)
        auto_stack_layout = QVBoxLayout(self.home_auto_stack)
        auto_stack_layout.setContentsMargins(0, 0, 0, 0)
        auto_stack_layout.setSpacing(30)
        auto_stack_layout.addWidget(self.home_runner_card)
        auto_stack_layout.addWidget(self.home_auto_panel)
        self.home_auto_stack.setVisible(False)

    def _create_home_tg_card(self) -> None:
        card = _Dark3DPanel()
        card.setObjectName("homeTgCard")
        card.setStyleSheet("QFrame#homeTgCard { background: transparent; border: none; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 23, 32, 26)
        lay.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("Telegram Proxy")
        title.setStyleSheet("color: #ffffff; font-size: 27px; font-weight: 800; background: transparent;")
        head.addWidget(title)
        head.addStretch(1)
        self.home_tg_status_dot = QLabel("●")
        self.home_tg_status_dot.setStyleSheet("color: #ff5c6c; font-size: 14px; background: transparent;")
        self.home_tg_status_label = QLabel("выключен")
        self.home_tg_status_label.setStyleSheet("color: #e8e8e8; font-size: 13px; font-weight: 600; background: transparent;")
        head.addWidget(self.home_tg_status_dot)
        head.addWidget(self.home_tg_status_label)
        lay.addLayout(head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(20)
        grid.setColumnStretch(1, 1)
        def _mk_key(text):
            lab = QLabel(text)
            lab.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: 700; background: transparent;")
            return lab
        def _mk_val():
            lab = QLabel("—")
            lab.setStyleSheet("color: rgba(255,255,255,0.78); font-size: 20px; background: transparent;")
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return lab
        self.home_tg_srv = _mk_val()
        self.home_tg_port = _mk_val()
        self.home_tg_secret = _mk_val()
        grid.addWidget(_mk_key("Server:"), 0, 0)
        grid.addWidget(self.home_tg_srv, 0, 1)
        grid.addWidget(_mk_key("Port:"), 1, 0)
        grid.addWidget(self.home_tg_port, 1, 1)
        grid.addWidget(_mk_key("Secret:"), 2, 0)
        grid.addWidget(self.home_tg_secret, 2, 1)
        lay.addLayout(grid)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_home_tg_open = QPushButton("Открыть Telegram")
        self.btn_home_tg_open.setObjectName("ghostBtn")
        self.btn_home_tg_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home_tg_open.clicked.connect(self.tg_open_in_telegram)
        self.btn_home_tg_more = QPushButton("Подробности  >>")
        self.btn_home_tg_more.setObjectName("ghostBtn")
        self.btn_home_tg_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_home_tg_more.clicked.connect(self._open_tg_tab)
        self.btn_home_tg_open.setFixedHeight(46)
        self.btn_home_tg_more.setFixedHeight(46)
        btns.addWidget(self.btn_home_tg_open, 1)
        btns.addWidget(self.btn_home_tg_more, 1)
        lay.addLayout(btns)
        self.home_tg_card = card

    def _create_home_zapret_card(self) -> None:
        card = _Dark3DPanel()
        card.setObjectName("homeZapCard")
        card.setStyleSheet("QFrame#homeZapCard { background: transparent; border: none; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 28, 32, 26)
        lay.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("Zapret")
        title.setStyleSheet("color: #ffffff; font-size: 27px; font-weight: 800; background: transparent;")
        head.addWidget(title)
        head.addStretch(1)
        self.home_zap_status_dot = QLabel("\u25cf")
        self.home_zap_status_dot.setStyleSheet("color: #ff5c6c; font-size: 14px; background: transparent;")
        self.home_zap_status_label = QLabel("\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d")
        self.home_zap_status_label.setStyleSheet("color: #e8e8e8; font-size: 13px; font-weight: 600; background: transparent;")
        head.addWidget(self.home_zap_status_dot)
        head.addWidget(self.home_zap_status_label)
        lay.addLayout(head)
        self.home_zap_strategy = QLabel("\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f: \u2014")
        self.home_zap_strategy.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 21px; font-weight: 600; background: transparent;")
        self.home_zap_strategy.setWordWrap(True)
        lay.addWidget(self.home_zap_strategy)
        self.home_zap_card = card

    def _build_action_decorations(self) -> None:
        specs = [
            ("btn_auto", "auto_select_icon_256.png", "\u0410\u0432\u0442\u043e\u043f\u043e\u0434\u0431\u043e\u0440", "\u041f\u043e\u0434\u0431\u043e\u0440 \u043b\u0443\u0447\u0448\u0435\u0439\n\u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438"),
            ("btn_check", "check_icon_256.png", "\u0422\u0435\u0441\u0442 \u043e\u0431\u0445\u043e\u0434\u0430", "\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0440\u0430\u0431\u043e\u0442\u044b\nZapret"),
        ]
        for attr, icon_name, title_text, sub_text in specs:
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            row = QHBoxLayout(btn)
            row.setContentsMargins(18, 12, 16, 12)
            row.setSpacing(14)
            icon = QLabel()
            pm = QPixmap(asset_path(icon_name))
            if not pm.isNull():
                icon.setPixmap(pm.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            icon.setFixedSize(60, 60)
            icon.setScaledContents(True)
            text_col = QVBoxLayout()
            text_col.setSpacing(3)
            title = QLabel(title_text)
            title.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: 700; background: transparent;")
            sub = QLabel(sub_text)
            sub.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 15px; background: transparent;")
            text_col.addStretch(1)
            text_col.addWidget(title)
            text_col.addWidget(sub)
            text_col.addStretch(1)
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
            row.addLayout(text_col, 1)
            for lbl in (icon, title, sub):
                lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                lbl.setVisible(False)
            setattr(self, attr + "_deco_icon", icon)
            setattr(self, attr + "_deco_title", title)
            setattr(self, attr + "_deco_sub", sub)

    def _set_action_deco(self, dark: bool) -> None:
        self._action_deco_active = dark
        for attr, plain in (("btn_auto", "\u0410\u0432\u0442\u043e\u043f\u043e\u0434\u0431\u043e\u0440"), ("btn_check", "\u0422\u0435\u0441\u0442 \u043e\u0431\u0445\u043e\u0434\u0430")):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            for suffix in ("_deco_icon", "_deco_title", "_deco_sub"):
                lbl = getattr(self, attr + suffix, None)
                if lbl is not None:
                    lbl.setVisible(dark)
            if dark:
                btn.setText("")
                btn.setMinimumHeight(120)
            else:
                btn.setText(plain)
                btn.setMinimumHeight(0)

    # Mascot frame -> asset file. Frames are decoded lazily and cached, so a
    # user who never opens the dark theme never pays for them.
    _HOME_CAT_ASSETS = {
        "open": "home_cat.png",
        "closed": "home_cat_closed.png",
        "search": "home_cat_search.png",
    }

    def _home_cat_frame_pixmap(self, frame: str = "open") -> QPixmap:
        """Return a mascot frame, decoding each file at most once."""
        cache = self.__dict__.setdefault("_home_cat_cache", {})
        pixmap = cache.get(frame)
        if pixmap is None:
            name = self._HOME_CAT_ASSETS.get(frame, self._HOME_CAT_ASSETS["open"])
            pixmap = QPixmap(asset_path(name))
            cache[frame] = pixmap
        return pixmap

    def _home_cat_scaled(self, frame: str, width: int, height: int) -> QPixmap:
        """Mascot frame pre-scaled to the label size, cached per size.

        ``QLabel.setScaledContents(True)`` rescales the pixmap on every repaint
        with a fast, non-smoothed transform. Scaling once with a smooth
        transform is both sharper and cheaper.
        """
        source = self._home_cat_frame_pixmap(frame)
        if source.isNull() or width <= 0 or height <= 0:
            return source
        cache = self.__dict__.setdefault("_home_cat_scaled_cache", {})
        key = (frame, width, height)
        scaled = cache.get(key)
        if scaled is None:
            scaled = source.scaled(
                width,
                height,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            cache[key] = scaled
        return scaled

    def _set_home_cat_frame(self, frame: str) -> bool:
        """Show ``frame`` on the mascot label. False when the asset is missing."""
        label = getattr(self, "home_cat", None)
        if label is None:
            return False
        size = label.size()
        pixmap = self._home_cat_scaled(frame, size.width(), size.height())
        if pixmap.isNull():
            return False
        label.setPixmap(pixmap)
        return True

    def _open_tg_tab(self) -> None:
        if hasattr(self, "tabs") and self.tabs.count():
            self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _home_parking(self) -> QWidget:
        """Hidden holder used to park widgets while the home tab is rebuilt.

        A widget with no parent becomes a top-level window, and Qt may flash it
        on screen for a frame before it is put back into a layout. Parking it
        inside a permanently hidden child widget avoids that flicker while
        keeping the widget's own show/hide state untouched.
        """
        holder = getattr(self, "_home_parking_widget", None)
        if holder is None:
            holder = QWidget(self)
            holder.setObjectName("homeParking")
            holder.hide()
            self._home_parking_widget = holder
        return holder

    def _detach_home_widgets(self, layout) -> None:
        park = self._home_parking()
        # Widgets the window keeps a Python reference to must survive the
        # rebuild: deleting them would leave dangling wrappers and crash with
        # "wrapped C/C++ object has been deleted". Only anonymous throwaway
        # containers created by the previous arrangement may be destroyed.
        keep = set()
        for value in vars(self).values():
            keep.add(id(value))
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    keep.add(id(item))
                    if isinstance(item, (list, tuple)):
                        keep.update(id(sub) for sub in item)
            elif isinstance(value, dict):
                keep.update(id(item) for item in value.values())
        while layout.count():
            item = layout.takeAt(0)
            wdg = item.widget()
            if wdg is not None:
                # Dark home layout wraps reusable widgets (PowerButton + cat)
                # inside a temporary container. When switching themes, Qt can
                # delete that container and its children, leaving Python with
                # a dangling "wrapped C/C++ object has been deleted" wrapper.
                # Detach those persistent widgets before orphaning the wrapper.
                for persistent in (
                    getattr(self, "btn_toggle", None),
                    getattr(self, "home_cat", None),
                    getattr(self, "sleep_z", None),
                ):
                    if persistent is not None and persistent.parent() is wdg:
                        persistent.setParent(park)
                wdg.setParent(park)
                if id(wdg) not in keep:
                    wdg.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                self._detach_home_widgets(sub)

    def _apply_home_layout(self, dark: bool = True) -> None:
        """Build the home page. Every theme uses the SAME arrangement.

        The layout used to be theme-dependent: a modern arrangement for the
        dark preset and an older "classic" one for every other theme. That is
        why non-dark themes looked broken -- the classic arrangement hid the
        mascot, the Telegram/Zapret cards, the auto-select block and the
        mini-game, and fell back to the legacy log panel. A theme must only
        change colors and the background image, never the arrangement, so
        there is exactly one layout now.

        ``dark`` is kept for call-site compatibility and is ignored.
        """
        if not hasattr(self, "home_body"):
            return
        if getattr(self, "_home_layout_built", False):
            return
        old = self.home_body.layout()
        if old is not None:
            self._detach_home_widgets(old)
            QWidget().setLayout(old)
        self._arrange_home()
        self._home_layout_built = True

    def _arrange_home(self) -> None:
        self.home_log.setVisible(False)
        auto_active = self._auto_thread is not None
        if hasattr(self, "home_tg_card"):
            self.home_tg_card.setVisible(not auto_active)
        self.run_title.setText("Zapret")
        self.run_title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root = QHBoxLayout(self.home_body)
        # Left inset folded into the power_wrap so the cat can peek further left
        # while the button/pill stay in their original screen positions.
        root.setContentsMargins(0, 30, 46, 34)
        root.setSpacing(30)
        left = QVBoxLayout()
        left.setSpacing(18)
        left.addStretch(1)
        wrap_w, wrap_h = 392, 460
        btn_w, btn_h = 234, 224
        btn_x = 58
        btn_y = wrap_h - btn_h - 52
        power_wrap = QWidget()
        power_wrap.setFixedSize(wrap_w, wrap_h)
        self.btn_toggle.setParent(power_wrap)
        self.btn_toggle.setStyleSheet(
            f"QPushButton#powerBtn {{ min-width: {btn_w}px; max-width: {btn_w}px; "
            f"min-height: {btn_h}px; max-height: {btn_h}px; }}"
        )
        self.btn_toggle.setMinimumSize(btn_w, btn_h)
        self.btn_toggle.setMaximumSize(btn_w, btn_h)
        self.btn_toggle.setFixedSize(btn_w, btn_h)
        self.btn_toggle.setGeometry(btn_x, btn_y, btn_w, btn_h)
        self.btn_toggle.show()
        base_cat = self._home_cat_frame_pixmap("open")
        if not base_cat.isNull():
            cat_w = 256
            cat_h = int(cat_w * base_cat.height() / max(1, base_cat.width()))
            # Big cat centered on the button: most of the head sits above the
            # button while the paws drape over its top edge (~34px overlap),
            # matching the reference composition.
            cat_y = max(0, btn_y + 44 - cat_h)
            self.home_cat.setParent(power_wrap)
            # Fix the size first so the cached scaled frame matches the label.
            self.home_cat.setFixedSize(cat_w, cat_h)
            self.home_cat.setPixmap(self._home_cat_scaled("open", cat_w, cat_h))
            self.home_cat.move((wrap_w - cat_w) // 2, cat_y)
            self.home_cat.setVisible(True)
            self.home_cat.raise_()
        else:
            self.home_cat.setVisible(False)
        # Sleeping symbols sit above/right of the cat without affecting its
        # geometry. Their state is refreshed by _set_power_state().
        self.sleep_z.setParent(power_wrap)
        self.sleep_z.setGeometry(220, 0, 140, 92)
        self.sleep_z.raise_()
        pw_row = QHBoxLayout()
        pw_row.addStretch(1)
        pw_row.addWidget(power_wrap)
        pw_row.addStretch(1)
        left.addLayout(pw_row)
        pill_row = QHBoxLayout()
        pill_row.addStretch(1)
        pill_row.addWidget(self.status_pill)
        pill_row.addStretch(1)
        left.addLayout(pill_row)
        left.addStretch(2)
        root.addLayout(left, 0)
        right = QVBoxLayout()
        right.setSpacing(20)  # keep the ~20pt gap between the two cards
        self.run_box.setVisible(False)
        self.run_box.setParent(self._home_parking())
        self._set_action_deco(True)
        # The game begins at the same vertical level as Telegram Proxy.
        self.home_right_top_spacer = QWidget()
        self.home_right_top_spacer.setFixedHeight(100)
        right.addWidget(self.home_right_top_spacer)
        if hasattr(self, "home_auto_stack"):
            right.addWidget(self.home_auto_stack, 0)
            self.home_auto_stack.setVisible(auto_active)
        # Cards hug their own content (cropped dark backdrop); the leftover
        # column space is absorbed by the stretch so the panels stay compact.
        if hasattr(self, "home_tg_card"):
            self.home_tg_card.setVisible(not auto_active)
            right.addWidget(self.home_tg_card, 0)
        if hasattr(self, "home_zap_card"):
            self.home_zap_card.setVisible(not auto_active)
            right.addWidget(self.home_zap_card, 0)
        bottom_group = QVBoxLayout()
        bottom_group.setSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(14)
        actions.addWidget(self.btn_auto, 1)
        actions.addWidget(self.btn_check, 1)
        bottom_group.addLayout(actions, 0)
        bottom_group.addWidget(self.btn_auto_cancel)
        bottom_group.addWidget(self.progress)
        bottom_group.addWidget(self.progress_label)
        right.addLayout(bottom_group, 0)
        right.addStretch(1)
        root.addLayout(right, 1)
        self._refresh_home_cards()

    def _refresh_home_cards(self) -> None:
        if not hasattr(self, "home_tg_srv"):
            return
        try:
            self.home_tg_srv.setText(str(tg_proxy.DEFAULT_HOST))
            self.home_tg_port.setText(str(tg_proxy.DEFAULT_PORT))
        except Exception:
            pass
        if hasattr(self, "tg_secret_value"):
            txt = self.tg_secret_value.text().strip()
            self.home_tg_secret.setText(txt if txt else "—")
        running = False
        try:
            running = bool(self.tg_runner.is_running())
        except Exception:
            running = False
        if running:
            self.home_tg_status_dot.setStyleSheet("color: #37c871; font-size: 14px; background: transparent;")
            self.home_tg_status_label.setText("\u0437\u0430\u043f\u0443\u0449\u0435\u043d")
        else:
            self.home_tg_status_dot.setStyleSheet("color: #ff5c6c; font-size: 14px; background: transparent;")
            self.home_tg_status_label.setText("\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d")
        if hasattr(self, "home_zap_status_dot"):
            zap_running = False
            zap_name = "\u2014"
            try:
                zap_running = bool(self.runner.is_running())
                strat = self.runner.current_strategy
                if strat is not None and getattr(strat, "name", None):
                    zap_name = strat.name
            except Exception:
                zap_running = False
            self.home_zap_strategy.setText("\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f: " + zap_name)
            if zap_running:
                self.home_zap_status_dot.setStyleSheet("color: #37c871; font-size: 14px; background: transparent;")
                self.home_zap_status_label.setText("\u0437\u0430\u043f\u0443\u0449\u0435\u043d")
            else:
                self.home_zap_status_dot.setStyleSheet("color: #ff5c6c; font-size: 14px; background: transparent;")
                self.home_zap_status_label.setText("\u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d")
