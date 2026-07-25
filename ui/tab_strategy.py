"""StrategyTabMixin — part of MainWindow, kept in its own file.

These methods were moved out of ui/main_window.py unchanged. They are
mixed into MainWindow, so ``self`` still refers to the window and every
attribute they use lives there as before.
"""
from __future__ import annotations


from PyQt6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout,
    QWidget,
)

from .theme import (
    smooth_code_font,
)
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


class StrategyTabMixin:
    """Mixin: see module docstring."""

    def _build_strategy_tab(self) -> QWidget:
        """Combined tab keeping the old Strategies / Editor / Logs together."""
        w = QWidget()
        w.setObjectName("strategyRoot")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(42, 12, 42, 18)
        lay.setSpacing(8)
        inner = QTabWidget()
        inner.setObjectName("innerTabs")
        inner.addTab(self._build_strategies_tab(), "\u0421\u043f\u0438\u0441\u043e\u043a")
        inner.addTab(self._build_editor_tab(), "\u0420\u0435\u0434\u0430\u043a\u0442\u043e\u0440")
        inner.addTab(self._build_logs_tab(), "\u041b\u043e\u0433\u0438")
        lay.addWidget(inner, 1)
        return w

    def _build_strategies_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("strategyPage")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(24, 12, 24, 16)
        lay.setSpacing(8)

        sel_row = QHBoxLayout()
        sel_title = QLabel("\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f:")
        sel_title.setObjectName("strategyLabel")
        sel_row.addWidget(sel_title)
        self.strategy_combo = QComboBox()
        self.strategy_combo.setObjectName("strategyCombo")
        self.strategy_combo.currentIndexChanged.connect(self._update_cmd_preview)
        sel_row.addWidget(self.strategy_combo, 1)
        lay.addLayout(sel_row)

        self.cmd_preview = QPlainTextEdit()
        self.cmd_preview.setObjectName("cmdPreview")
        self.cmd_preview.setReadOnly(True)
        self.cmd_preview.setFont(smooth_code_font(10))
        self.cmd_preview.setFixedHeight(84)
        self.cmd_preview.setToolTip("\u041a\u043e\u043c\u0430\u043d\u0434\u0430, \u043a\u043e\u0442\u043e\u0440\u0430\u044f \u0431\u0443\u0434\u0435\u0442 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u0430")
        lay.addWidget(self.cmd_preview)
        lay.addSpacing(6)

        list_title = QLabel("\u0414\u043e\u0441\u0442\u0443\u043f\u043d\u044b\u0435 \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438:")
        list_title.setObjectName("strategyLabel")
        lay.addWidget(list_title)
        self.strategy_list = QListWidget()
        self.strategy_list.setObjectName("strategyList")
        self.strategy_list.currentRowChanged.connect(self._on_strategy_selected)
        self.strategy_list.itemDoubleClicked.connect(lambda _i: self._run_selected_from_list())
        lay.addWidget(self.strategy_list, 1)
        # Keep the detail widget for the existing selection logic, but hide it:
        # the previous visible panel looked empty and stole height from the
        # available strategies list.
        self.strategy_detail = QPlainTextEdit()
        self.strategy_detail.setObjectName("strategyDetail")
        self.strategy_detail.setReadOnly(True)
        self.strategy_detail.setFont(smooth_code_font(12))
        self.strategy_detail.hide()
        row = QHBoxLayout()
        self.btn_reload = QPushButton("\u041e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043e\u043a")
        self.btn_reload.setObjectName("strategySoftBtn")
        self.btn_reload.clicked.connect(lambda: self.reload_strategies(rebuild=True))
        self.btn_run_list = QPushButton("\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u0443\u044e")
        self.btn_run_list.setObjectName("strategyPrimaryBtn")
        self.btn_run_list.clicked.connect(self._run_selected_from_list)
        row.addWidget(self.btn_reload)
        row.addStretch(1)
        row.addWidget(self.btn_run_list)
        lay.addLayout(row)
        return w

    def _build_editor_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("strategyPage")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(34, 26, 34, 28)
        lay.setSpacing(14)

        custom_box = QGroupBox("\u0421\u0432\u043e\u044f \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u044f (\u0430\u0440\u0433\u0443\u043c\u0435\u043d\u0442\u044b winws.exe)")
        custom_box.setObjectName("strategyBox")
        cbx = QVBoxLayout(custom_box)
        self.edit_name = QLineEdit()
        self.edit_name.setObjectName("strategyInput")
        self.edit_name.setPlaceholderText("\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0441\u0442\u0440\u0430\u0442\u0435\u0433\u0438\u0438")
        cbx.addWidget(self.edit_name)
        self.edit_args = QPlainTextEdit()
        self.edit_args.setObjectName("strategyCodeEdit")
        self.edit_args.setFont(smooth_code_font(12))
        self.edit_args.setPlaceholderText("--wf-tcp=80,443 --dpi-desync=fake,split2 ...")
        cbx.addWidget(self.edit_args, 1)
        row = QHBoxLayout()
        btn_validate = QPushButton("\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c")
        btn_validate.setObjectName("strategyEditorBtn")
        btn_validate.clicked.connect(self._validate_custom)
        btn_save = QPushButton("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c")
        btn_save.setObjectName("strategyEditorBtn")
        btn_save.clicked.connect(self._save_custom)
        btn_del = QPushButton("\u0423\u0434\u0430\u043b\u0438\u0442\u044c")
        btn_del.setObjectName("strategyEditorBtn")
        btn_del.clicked.connect(self._delete_custom)
        row.addWidget(btn_validate)
        row.addStretch(1)
        row.addWidget(btn_del)
        row.addWidget(btn_save)
        cbx.addLayout(row)
        lay.addWidget(custom_box, 1)

        dom_box = QGroupBox("\u0421\u043f\u0438\u0441\u043a\u0438 \u0434\u043e\u043c\u0435\u043d\u043e\u0432 / ipset")
        dom_box.setObjectName("strategyBox")
        dbx = QVBoxLayout(dom_box)
        self.domain_combo = QComboBox()
        self.domain_combo.setObjectName("strategyCombo")
        # Keep the popup inside the app window area instead of letting it grow
        # past the bottom edge when many domain/ipset files are available.
        self.domain_combo.setMaxVisibleItems(5)
        self.domain_combo.currentIndexChanged.connect(self._load_domain_file)
        dbx.addWidget(self.domain_combo)
        self.domain_text = QPlainTextEdit()
        self.domain_text.setObjectName("strategyCodeEdit")
        self.domain_text.setFont(smooth_code_font(12))
        dbx.addWidget(self.domain_text, 1)
        save_dom = QPushButton("\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u0441\u043f\u0438\u0441\u043e\u043a")
        save_dom.setObjectName("strategyEditorBtn")
        save_dom.clicked.connect(self._save_domain_file)
        dbx.addWidget(save_dom)
        lay.addWidget(dom_box, 1)
        return w
