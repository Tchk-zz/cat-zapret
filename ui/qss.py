"""Qt style sheets for the built-in themes.

WIN11_DARK_QSS extends DARK_QSS with overrides.
WIN11_LIGHT_QSS is standalone: it must not inherit dark colours.
"""

DARK_QSS = """
* { font-family: 'Unbounded', 'Segoe UI', 'Inter', sans-serif; font-size: 14px; }

QMainWindow, QWidget { color: #ece8ff; }
QMainWindow { background: #0c0a24; }

/* Main surface: diagonal purple/blue gradient like the mockup. */
QTabWidget::pane {
    border: none;
    background: transparent;
    border-radius: 16px;
}
QWidget#homeRoot { background: transparent; }
QTabWidget { background: transparent; }

/* Top navigation rendered as a single iOS-26-style "liquid glass" segmented
   panel: one frosted capsule containing all sections, with the active section
   highlighted by a brighter glass pill. */
QFrame#navPanel {
    background: rgba(255,255,255,0.16);
    border: 1px solid rgba(255,255,255,0.24);
    border-radius: 18px;
}
QFrame#navIndicator {
    background: rgba(255,255,255,0.26);
    border: 1px solid rgba(255,255,255,0.40);
    border-radius: 12px;
}
QPushButton#navBtn {
    background: transparent;
    color: #cfc7ee;
    padding: 12px 46px;
    border: 1px solid transparent;
    border-radius: 12px;
    font-size: 19px; font-weight: 500;
}
QPushButton#navBtn:hover:!checked { background: rgba(255,255,255,0.10); color: #ffffff; }
QPushButton#navBtn:checked { color: #ffffff; }

/* Inner tabs (List / Editor / Logs) inside the Strategy tab. */
QTabWidget#innerTabs::pane {
    background: rgba(34, 16, 92, 0.30);
    border: none;
    border-radius: 22px;
    top: -1px;
}
QTabWidget#innerTabs::tab-bar {
    alignment: center;
}
QTabWidget#innerTabs QTabBar::tab {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.76);
    border-radius: 15px;
    padding: 9px 58px;
    margin: 0 8px 8px 8px;
    color: rgba(255,255,255,0.92);
    font-size: 19px;
    font-weight: 700;
}
QTabWidget#innerTabs QTabBar::tab:selected {
    background: rgba(255,255,255,0.28);
    color: #ffffff;
}
QTabWidget#innerTabs QTabBar::tab:hover:!selected {
    background: rgba(255,255,255,0.20);
}

/* Central power button. */
QPushButton#powerBtn {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 32px;
    min-width: 160px; max-width: 160px;
    min-height: 160px; max-height: 160px;
    font-size: 70px;
    color: #d9ccff;
}
QPushButton#powerBtn:hover { background: rgba(255,255,255,0.10); }
QPushButton#powerBtn:pressed { background: rgba(255,255,255,0.14); }
QPushButton#powerBtn[running="true"] {
    color: #8af0b0;
    border: 1px solid rgba(120,240,170,0.55);
    background: rgba(80,220,140,0.10);
}

/* Status pill. */
QFrame#statusPill { background: rgba(18,12,38,0.34); border: none; border-radius: 16px; }
QFrame#statusPill QLabel#statusText { color: #f4f1ff; font-size: 15px; font-weight: 600; }
QLabel#statusDot { font-size: 16px; }

/* Glass action buttons (transparent, matching the rest of the UI). */
QPushButton#gradBtn {
    background: rgba(255,255,255,0.30);
    border: 1px solid rgba(255,255,255,0.46); border-radius: 18px;
    padding: 20px 22px 20px 18px; text-align: left;
    color: #f2eeff; font-size: 18px; font-weight: 500;
    min-width: 205px;
}
QPushButton#gradBtn:hover {
    background: rgba(255,255,255,0.42);
    border-color: rgba(255,255,255,0.68);
}
QPushButton#gradBtn:pressed {
    background: rgba(255,255,255,0.34);
}
QPushButton#gradBtn:disabled { background: rgba(255,255,255,0.04); color: #9b93c0; }

QPushButton#ghostBtn {
    background: rgba(255,90,108,0.16); color: #ffb3bc;
    border: 1px solid rgba(255,90,108,0.45); border-radius: 14px; padding: 12px 18px;
}
QPushButton#ghostBtn:hover { background: rgba(255,90,108,0.26); }

/* Running-strategy block + log. */
/* Frosted glass card behind the home action buttons (iOS-26 concept). */
QFrame#glassCard {
    background: rgba(255,255,255,0.08);
    border: none;
    border-radius: 22px;
}

QFrame#runBox {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 18px;
}
QLabel#runTitle { color: #d7cffb; font-weight: 500; }
QLineEdit#runField {
    background: rgba(255,255,255,0.10); border: none; border-radius: 12px;
    padding: 9px 12px; color: #f2eeff; font-weight: 600; font-size: 20px;
}
QTextEdit#homeLog {
    background: rgba(12,10,36,0.55); border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px; color: #c7bfe6; padding: 10px;
    font-family: 'Consolas','Cascadia Mono',monospace; font-size: 14px;
}

/* Group boxes and generic controls. */
QGroupBox {
    border: 1px solid rgba(255,255,255,0.10); border-radius: 14px;
    margin-top: 14px; padding: 12px; background: rgba(255,255,255,0.04);
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #b9b0e0; font-weight: 700; }

QPushButton {
    background: rgba(255,255,255,0.07); color: #ece8ff; border: 1px solid rgba(255,255,255,0.14);
    border-radius: 12px; padding: 9px 16px; font-weight: 500;
}
QPushButton:hover { background: rgba(255,255,255,0.12); }
QPushButton:pressed { background: rgba(255,255,255,0.16); }
QPushButton:disabled { color: #8a82ad; background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.06); }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b14bf0, stop:1 #7d52ff);
    border: none; color: white; font-weight: 500;
}
QPushButton#primary:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #be63f5, stop:1 #8d66ff); }
QPushButton#primary:disabled { background: rgba(255,255,255,0.08); color: #9b93c0; }
QPushButton#danger { background: #e0455a; border: none; color: white; font-weight: 500; }
QPushButton#danger:hover { background: #ee5568; }
/* Telegram tab buttons */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b14bf0, stop:1 #7d52ff);
    border: none; color: white; font-weight: 600;
    border-radius: 12px; padding: 9px 18px;
}
QPushButton#primaryBtn:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #be63f5, stop:1 #8d66ff); }
QPushButton#primaryBtn:pressed { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #9d3ee0, stop:1 #6d42ef); }
QPushButton#primaryBtn:disabled { background: rgba(255,255,255,0.08); color: #9b93c0; }
QPushButton#secondaryBtn {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.18);
    color: #ece8ff; font-weight: 500;
    border-radius: 12px; padding: 9px 16px;
}
QPushButton#secondaryBtn:hover { background: rgba(255,255,255,0.16); border-color: rgba(255,255,255,0.35); }
QPushButton#secondaryBtn:pressed { background: rgba(255,255,255,0.22); }
QPushButton#secondaryBtn:disabled { background: rgba(255,255,255,0.04); color: #8a82ad; border-color: rgba(255,255,255,0.06); }

QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QSpinBox {
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);
    border-radius: 10px; padding: 7px; color: #ece8ff;
    selection-background-color: #7d52ff;
}
QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {
    border: 1px solid #9d6bff;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #1c1640; color: #ece8ff; border: 1px solid rgba(255,255,255,0.14);
    selection-background-color: #7d52ff; border-radius: 8px;
}
QListWidget::item { padding: 7px 5px; border-radius: 8px; }
QListWidget::item:selected { background: #7d52ff; color: white; }
QListWidget::item:hover { background: rgba(255,255,255,0.10); }

QPlainTextEdit#cmdPreview { font-family: 'Consolas','Cascadia Mono',monospace; font-size: 12px; color: #cfc7ee; }

/* Strategy page: same image-backed glass language as Settings, while keeping
   the full existing Strategy/List/Editor/Logs functionality. */
QWidget#strategyRoot,
QWidget#strategyPage {
    background: transparent;
}
QLabel#strategyLabel {
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
}
QComboBox#strategyCombo,
QLineEdit#strategyInput {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.34);
    border-radius: 12px;
    padding: 9px 12px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 500;
}
QComboBox#strategyCombo:hover,
QLineEdit#strategyInput:hover {
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.54);
}
QListWidget#strategyList {
    background: transparent;
    border: none;
    border-radius: 16px;
    outline: none;
    padding: 14px 22px;
    color: #ffffff;
    font-size: 16px;
    font-weight: 600;
}
QListWidget#strategyList::item {
    padding: 7px 10px;
    border-radius: 10px;
}
QListWidget#strategyList::item:hover {
    background: rgba(255,255,255,0.18);
}
QListWidget#strategyList::item:selected {
    background: rgba(255, 126, 226, 0.34);
    color: #ffffff;
}
QListWidget#strategyList::item:selected:active,
QListWidget#strategyList::item:selected:!active {
    background: rgba(255, 126, 226, 0.34);
    color: #ffffff;
    border: none;
    outline: none;
}
QPlainTextEdit#cmdPreview,
QPlainTextEdit#strategyDetail,
QPlainTextEdit#strategyCodeEdit,
QTextEdit#logView {
    background: rgba(14, 7, 48, 0.48);
    border: 1px solid rgba(255,255,255,0.20);
    border-radius: 14px;
    padding: 8px 14px 8px 10px;
    color: #eee8ff;
    font-family: 'Cascadia Mono','Consolas','Liberation Mono',monospace;
    font-size: 16px;
}
QPlainTextEdit#cmdPreview {
    font-size: 14px;
}
QGroupBox#strategyBox {
    background: transparent;
    border: none;
    border-radius: 18px;
    margin-top: 18px;
    padding: 18px;
    color: #ffffff;
    font-weight: 700;
}
QGroupBox#strategyBox::title {
    subcontrol-origin: margin;
    left: 18px;
    padding: 0 8px;
    color: rgba(255,255,255,0.92);
    font-weight: 700;
}
QPushButton#strategySoftBtn,
QPushButton#strategyPrimaryBtn,
QPushButton#strategyDangerBtn {
    border-radius: 13px;
    padding: 10px 18px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#strategySoftBtn {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.38);
}
QPushButton#strategySoftBtn:hover {
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.62);
}
QPushButton#strategyPrimaryBtn {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.42);
}
QPushButton#strategyPrimaryBtn:hover {
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.70);
}
QPushButton#strategyDangerBtn {
    background: transparent;
    border: 1px solid rgba(255,255,255,0.34);
}
QPushButton#strategyDangerBtn:hover {
    background: rgba(255,255,255,0.06);
    border-color: rgba(255,255,255,0.62);
}
QPushButton#strategyEditorBtn {
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.42);
    border-radius: 13px;
    padding: 10px 18px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#strategyEditorBtn:hover {
    background: rgba(255,255,255,0.24);
    border-color: rgba(255,255,255,0.68);
}
QPushButton#strategyEditorBtn:pressed {
    background: rgba(255,255,255,0.18);
}

/* Code & log areas keep a monospace font (not Unbounded) for readability. */
QPlainTextEdit, QTextEdit#logView { font-family: 'Consolas','Cascadia Mono',monospace; }
QTextEdit#logView { font-size: 12px; }

QProgressBar {
    background: rgba(255,255,255,0.08); border: none; border-radius: 7px;
    height: 12px; text-align: center; color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #b14bf0, stop:1 #7d52ff);
    border-radius: 7px;
}

QCheckBox { spacing: 8px; padding: 3px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid rgba(255,255,255,0.40); background: rgba(255,255,255,0.06); }
QCheckBox::indicator:hover { border-color: rgba(255,255,255,0.70); }
QCheckBox::indicator:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #c44bff, stop:1 #7d52ff); border: 2px solid #ffffff; }

/* Settings tab: image-backed iOS-26 frosted panel, matching the reference. */
QWidget#settingsRoot { background: transparent; }
QFrame#settingsCard {
    background: rgba(16, 8, 56, 0.42);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 28px;
}
QFrame#settingsRow {
    background: rgba(255,255,255,0.24);
    border: none;
    border-radius: 12px;
}
QFrame#settingsRow:hover {
    background: rgba(255,255,255,0.31);
}
QCheckBox#settingsCheck,
QCheckBox#settingsThemeCheck {
    color: #ffffff;
    font-size: 16px;
    font-weight: 500;
    spacing: 8px;
    padding: 0;
}
QCheckBox#settingsCheck::indicator,
QCheckBox#settingsThemeCheck::indicator {
    width: 21px;
    height: 21px;
    border-radius: 5px;
    border: 2px solid rgba(255,180,255,0.95);
    background: rgba(255,255,255,0.05);
}
QCheckBox#settingsCheck::indicator:hover,
QCheckBox#settingsThemeCheck::indicator:hover {
    background: rgba(255,255,255,0.16);
    border-color: rgba(255,255,255,0.95);
}
QCheckBox#settingsCheck::indicator:checked,
QCheckBox#settingsThemeCheck::indicator:checked {
    background: rgba(255,180,255,0.95);
    border: 2px solid rgba(255,220,255,1.0);
}
QLabel#settingsThemeTitle {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
    margin-top: 4px;
}

QPushButton#settingsLangBtn {
    background: rgba(255,255,255,0.14);
    border: 1px solid rgba(255,210,255,0.76);
    border-radius: 14px;
    color: #ffd6ff;
    font-size: 13px;
    font-weight: 800;
    min-width: 46px;
    max-width: 46px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
}
QPushButton#settingsLangBtn:hover {
    background: rgba(255,255,255,0.24);
    color: #ffffff;
    border-color: rgba(255,255,255,0.96);
}

QPushButton#settingsSoftBtn {
    background: rgba(255,255,255,0.50);
    border: 2px solid rgba(255,255,255,0.92);
    border-radius: 13px;
    padding: 7px 18px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}
QPushButton#settingsSoftBtn:hover {
    background: rgba(255,255,255,0.60);
    border-color: rgba(255,255,255,1.0);
}
QPushButton#settingsSoftBtn:pressed {
    background: rgba(255,255,255,0.54);
}
QPushButton#settingsPrimaryBtn {
    background: rgba(104, 185, 216, 0.78);
    border: 2px solid rgba(225,245,255,0.98);
    border-radius: 13px;
    padding: 7px 18px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}
QPushButton#settingsPrimaryBtn:hover {
    background: rgba(123, 205, 232, 0.90);
    border-color: rgba(255,255,255,1.0);
}
QPushButton#settingsPrimaryBtn:pressed {
    background: rgba(94, 175, 210, 0.86);
}



/* Games & Services tab: compact two-column card on the Settings background. */
QWidget#gamesRoot {
    background: transparent;
}
QLabel#gamesTitle {
    color: #ffffff;
    font-size: 29px;
    font-weight: 650;
}
QLabel#gamesSubtitle {
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}
QFrame#gamesCard {
    background: rgba(16, 8, 56, 0.50);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 30px;
}
QFrame#gamesColumn {
    background: transparent;
    border: none;
}
QWidget#gamesColumnIcon {
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
}
QLabel#gamesColumnTitle {
    color: rgba(255, 185, 255, 0.94);
    font-size: 19px;
    font-weight: 600;
}
QCheckBox#gamesCheck {
    color: #ffffff;
    font-size: 22px;
    font-weight: 500;
    spacing: 8px;
    padding: 0;
}
QCheckBox#gamesCheck::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 2px solid rgba(255,255,255,0.95);
    background: transparent;
}
QCheckBox#gamesCheck::indicator:hover {
    background: rgba(255,255,255,0.13);
}
QCheckBox#gamesCheck::indicator:checked {
    background: rgba(238, 126, 255, 0.96);
    border: 2px solid rgba(238, 126, 255, 0.96);
}
QWidget#gamesDomainBlock {
    background: transparent;
    margin-top: 0;
}
QLabel#gamesDomainLabel {
    color: #ffffff;
    font-size: 14px;
    font-weight: 650;
    padding-left: 10px;
    margin-bottom: 0;
}
QLineEdit#gamesInput {
    background: rgba(12, 4, 44, 0.54);
    border: 1px solid rgba(255,255,255,0.84);
    border-radius: 8px;
    padding: 3px 10px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 500;
    min-height: 18px;
    max-height: 24px;
}
QLineEdit#gamesInput:focus {
    border: 1px solid rgba(255,210,255,1.0);
    background: rgba(18, 6, 58, 0.70);
}
QFrame#gamesDivider {
    background: rgba(255,255,255,0.78);
    border: none;
    min-width: 1px;
    max-width: 1px;
}
QLabel#gamesNote {
    color: rgba(255,185,255,0.90);
    font-size: 13pt;
    font-weight: 500;
    margin-top: -4px;
    min-height: 30px;
    padding: 0 10px 2px 10px;
}
QGroupBox#gamesFilterBox {
    background: transparent;
    border: none;
    border-radius: 16px;
    margin-top: 0px;
    color: #ffffff;
    font-size: 19px;
    font-weight: 650;
}
QGroupBox#gamesFilterBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    top: -4px;
    padding: 0 8px;
    color: #ffffff;
    font-size: 18px;
    font-weight: 650;
}
QCheckBox#gamesFilterCheck {
    color: #ffffff;
    font-size: 13px;
    font-weight: 500;
    spacing: 7px;
    padding: 0;
}
QCheckBox#gamesFilterCheck::indicator {
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 2px solid rgba(255,255,255,0.92);
    background: transparent;
}
QCheckBox#gamesFilterCheck::indicator:checked {
    background: rgba(238, 126, 255, 0.96);
    border-color: rgba(238, 126, 255, 0.96);
}
QLabel#gamesFilterWarn {
    color: rgba(255,255,255,0.84);
    font-size: 12px;
    font-weight: 500;
}

QScrollArea#tabScroll { background: transparent; border: none; }
QScrollArea#tabScroll > QWidget > QWidget { background: transparent; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #b172ff; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #d0a3ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #b172ff; border-radius: 4px; min-width: 28px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QLabel#h1 { font-size: 22px; font-weight: 500; }
QLabel#subtitle { color: #b9b0e0; font-size: 13px; font-weight: 500; }
QLabel#muted { color: #9b93c0; }
/* Small captions on the Telegram tab (Server / Port / Secret / hints). */
QLabel#tgFieldLabel { color: rgba(255,255,255,0.65); }
QToolTip { background: #211a44; color: #ece8ff; border: 1px solid rgba(255,255,255,0.18); padding: 6px; border-radius: 6px; }
"""


WIN11_DARK_QSS = DARK_QSS + """
/* Windows 11-like neutral dark theme: no purple/pink accents, no gradients. */
QMainWindow, QWidget { color: #f3f3f3; }
QMainWindow { background: #0f0f0f; }
QFrame#navPanel, QFrame#navIndicator,
QFrame#settingsCard, QFrame#gamesCard, QFrame#runBox,
QTabWidget#innerTabs::pane {
    background: #1f1f1f;
    border: 1px solid #3a3a3a;
    border-radius: 14px;
}
QFrame#navIndicator { background: #323232; }
QPushButton#navBtn { color: #dcdcdc; background: transparent; border: none; }
QPushButton#navBtn:hover:!checked { background: #2a2a2a; color: #ffffff; }
QPushButton#navBtn:checked { color: #ffffff; background: transparent; }

QPushButton#gradBtn,
QPushButton#ghostBtn,
QPushButton#settingsSoftBtn,
QPushButton#settingsPrimaryBtn,
QPushButton#settingsLangBtn,
QPushButton#strategySoftBtn,
QPushButton#strategyPrimaryBtn,
QPushButton#strategyDangerBtn,
QPushButton#strategyEditorBtn,
QPushButton#popupOk,
QPushButton#popupCancel,
QPushButton {
    background: #2d2d2d;
    color: #ffffff;
    border: 1px solid #5a5a5a;
    border-radius: 8px;
}
QPushButton:hover, QPushButton#gradBtn:hover, QPushButton#ghostBtn:hover,
QPushButton#settingsSoftBtn:hover, QPushButton#settingsPrimaryBtn:hover,
QPushButton#settingsLangBtn:hover,
QPushButton#strategySoftBtn:hover, QPushButton#strategyPrimaryBtn:hover,
QPushButton#strategyDangerBtn:hover, QPushButton#strategyEditorBtn:hover,
QPushButton#popupOk:hover, QPushButton#popupCancel:hover {
    background: #3a3a3a;
    border-color: #777777;
    color: #ffffff;
}
QPushButton:pressed { background: #252525; }
QPushButton:disabled, QPushButton#gradBtn:disabled { background: #1d1d1d; color: #777777; border-color: #333333; }

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget,
QLineEdit#runField, QPlainTextEdit#cmdPreview, QPlainTextEdit#strategyDetail,
QPlainTextEdit#strategyCodeEdit, QTextEdit#logView, QTextEdit#homeLog,
QComboBox#strategyCombo, QLineEdit#strategyInput, QLineEdit#gamesInput {
    background: #181818;
    border: 1px solid #3f3f3f;
    color: #f3f3f3;
    selection-background-color: #ffffff;
    selection-color: #000000;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox#strategyCombo:focus, QLineEdit#strategyInput:focus, QLineEdit#gamesInput:focus {
    border: 1px solid #ffffff;
    background: #1f1f1f;
}
QComboBox QAbstractItemView { background: #1f1f1f; color: #ffffff; selection-background-color: #3a3a3a; }
QListWidget::item:selected, QListWidget#strategyList::item:selected,
QListWidget#strategyList::item:selected:active, QListWidget#strategyList::item:selected:!active {
    background: #3a3a3a;
    color: #ffffff;
}
QListWidget::item:hover, QListWidget#strategyList::item:hover { background: #2a2a2a; }

QLabel#runTitle, QLabel#statusText, QLabel#strategyLabel, QLabel#settingsThemeTitle,
QLabel#gamesTitle, QLabel#gamesSubtitle, QLabel#gamesColumnTitle, QLabel#gamesDomainLabel,
QLabel#gamesNote, QLabel#gamesFilterWarn, QLabel#popupTitle, QLabel#popupBody,
QLabel#popupPercent, QLabel#popupDetail, QLabel#muted,
QCheckBox#settingsCheck, QCheckBox#settingsThemeCheck, QCheckBox#gamesCheck,
QCheckBox#gamesFilterCheck, QGroupBox#gamesFilterBox, QGroupBox#strategyBox {
    color: #ffffff;
}

QPushButton#gradBtn {
    background: #2d2d2d;
    color: #ffffff;
    border: 1px solid #5a5a5a;
    border-radius: 18px;
    padding: 20px 22px 20px 18px;
    text-align: left;
    min-width: 205px;
    min-height: 64px;
    font-size: 18px;
    font-weight: 500;
}
QPushButton#gradBtn:hover { background: #3a3a3a; border-color: #777777; }
QPushButton#gradBtn:pressed { background: #252525; }
QPushButton#gradBtn:disabled { background: #1d1d1d; color: #777777; border-color: #333333; }

QFrame#settingsRow { background: #252525; border: 1px solid #3a3a3a; }
QFrame#settingsRow:hover { background: #2c2c2c; }
QGroupBox, QGroupBox#strategyBox, QGroupBox#gamesFilterBox { background: transparent; border-color: #3a3a3a; color: #ffffff; }
QGroupBox::title, QGroupBox#strategyBox::title, QGroupBox#gamesFilterBox::title { color: #ffffff; }

QCheckBox::indicator, QCheckBox#settingsCheck::indicator, QCheckBox#settingsThemeCheck::indicator,
QCheckBox#gamesCheck::indicator, QCheckBox#gamesFilterCheck::indicator {
    background: #1a1a1a;
    border: 1px solid #777777;
    border-radius: 4px;
}
QCheckBox::indicator:hover, QCheckBox#settingsCheck::indicator:hover, QCheckBox#settingsThemeCheck::indicator:hover,
QCheckBox#gamesCheck::indicator:hover, QCheckBox#gamesFilterCheck::indicator:hover {
    background: #262626;
    border-color: #ffffff;
}
QCheckBox::indicator:checked, QCheckBox#settingsCheck::indicator:checked, QCheckBox#settingsThemeCheck::indicator:checked,
QCheckBox#gamesCheck::indicator:checked, QCheckBox#gamesFilterCheck::indicator:checked {
    background: #ffffff;
    border: 1px solid #ffffff;
}
QProgressBar, QProgressBar#popupProgress { background: #252525; border: 1px solid #4a4a4a; border-radius: 4px; color: transparent; }
QProgressBar::chunk, QProgressBar#popupProgress::chunk { background: #ffffff; border-radius: 4px; }
QFrame#gamesDivider { background: #4a4a4a; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #5a5a5a; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #777777; }
QLabel#tgFieldLabel { color: #c8c8c8; }
QToolTip { background: #202020; color: #ffffff; border: 1px solid #4a4a4a; }
"""


WIN11_LIGHT_QSS = """
/* Windows 11-like neutral light theme: black accents, gray/white surfaces,
   no gradients.

   This sheet is standalone on purpose: it does NOT extend DARK_QSS, so no dark
   colour can leak into the light theme (white-on-white text). Every selector
   used by the app is redefined here with light colours. */
* { font-family: 'Unbounded', 'Segoe UI', 'Inter', sans-serif; font-size: 14px; }

QMainWindow, QWidget { color: #111111; }
QMainWindow { background: #f3f3f3; }

QTabWidget::pane { border: none; background: transparent; border-radius: 16px; }
QTabWidget { background: transparent; }
QWidget#homeRoot { background: transparent; }
QWidget#strategyRoot, QWidget#strategyPage, QWidget#settingsRoot, QWidget#gamesRoot { background: transparent; }

/* Top navigation. */
QFrame#navPanel { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 18px; }
QFrame#navIndicator { background: #e9e9e9; border: 1px solid #d5d5d5; border-radius: 12px; }
QPushButton#navBtn {
    background: transparent;
    color: #1a1a1a;
    padding: 12px 46px;
    border: 1px solid transparent;
    border-radius: 12px;
    font-size: 19px; font-weight: 500;
}
QPushButton#navBtn:hover:!checked { background: #eeeeee; color: #000000; }
QPushButton#navBtn:checked { color: #000000; background: transparent; }

/* Inner tabs (List / Editor / Logs). */
QTabWidget#innerTabs::pane { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 22px; top: -1px; }
QTabWidget#innerTabs::tab-bar { alignment: center; }
QTabWidget#innerTabs QTabBar::tab {
    background: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 15px;
    padding: 9px 58px;
    margin: 0 8px 8px 8px;
    color: #000000;
    font-size: 19px;
    font-weight: 700;
}
QTabWidget#innerTabs QTabBar::tab:selected { background: #e9e9e9; color: #000000; }
QTabWidget#innerTabs QTabBar::tab:hover:!selected { background: #f2f2f2; color: #000000; }

/* Central power button. */
QPushButton#powerBtn {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 32px;
    min-width: 160px; max-width: 160px;
    min-height: 160px; max-height: 160px;
    font-size: 70px;
    color: #3a3a3a;
}
QPushButton#powerBtn:hover { background: #f2f2f2; }
QPushButton#powerBtn:pressed { background: #e8e8e8; }
QPushButton#powerBtn[running="true"] { color: #14804a; border: 1px solid #14804a; background: #eaf7ef; }

/* Status pill. */
QFrame#statusPill { background: #ffffff; border: 1px solid #e2e2e2; border-radius: 16px; }
QFrame#statusPill QLabel#statusText { color: #000000; font-size: 15px; font-weight: 600; }
QLabel#statusDot { font-size: 16px; }

/* Home cards and action buttons. */
QFrame#glassCard { background: #ffffff; border: 1px solid #e2e2e2; border-radius: 22px; }
QFrame#runBox { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 18px; }
QLabel#runTitle { color: #333333; font-weight: 500; }
QLineEdit#runField {
    background: #f3f3f3; border: 1px solid #d6d6d6; border-radius: 12px;
    padding: 9px 12px; color: #111111; font-weight: 600; font-size: 20px;
}
QTextEdit#homeLog {
    background: #ffffff; border: 1px solid #d6d6d6;
    border-radius: 14px; color: #333333; padding: 10px;
    font-family: 'Consolas','Cascadia Mono',monospace; font-size: 14px;
}

QPushButton#gradBtn {
    background: #ffffff;
    color: #000000;
    border: 1px solid #b8b8b8;
    border-radius: 18px;
    padding: 20px 22px 20px 18px;
    text-align: left;
    min-width: 205px;
    font-size: 18px;
    font-weight: 500;
}
QPushButton#gradBtn:hover { background: #f2f2f2; border-color: #8a8a8a; }
QPushButton#gradBtn:pressed { background: #e8e8e8; }
QPushButton#gradBtn:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }

QPushButton#ghostBtn {
    background: #fdecee; color: #b3261e;
    border: 1px solid #e5a1a6; border-radius: 14px; padding: 12px 18px;
}
QPushButton#ghostBtn:hover { background: #fadcdf; }

/* Group boxes and generic controls. */
QGroupBox {
    border: 1px solid #d0d0d0; border-radius: 14px;
    margin-top: 14px; padding: 12px; background: transparent; color: #000000;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #000000; font-weight: 700; }

QPushButton {
    background: #ffffff; color: #000000; border: 1px solid #b8b8b8;
    border-radius: 12px; padding: 9px 16px; font-weight: 500;
}
QPushButton:hover { background: #f2f2f2; border-color: #777777; color: #000000; }
QPushButton:pressed { background: #e8e8e8; }
QPushButton:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }
QPushButton#primary, QPushButton#primaryBtn {
    background: #1a1a1a; border: 1px solid #1a1a1a; color: #ffffff; font-weight: 600;
    border-radius: 12px; padding: 9px 18px;
}
QPushButton#primary:hover, QPushButton#primaryBtn:hover { background: #333333; border-color: #333333; color: #ffffff; }
QPushButton#primary:pressed, QPushButton#primaryBtn:pressed { background: #000000; }
QPushButton#primary:disabled, QPushButton#primaryBtn:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }
QPushButton#danger { background: #c0392b; border: 1px solid #c0392b; color: #ffffff; font-weight: 500; }
QPushButton#danger:hover { background: #d0453a; color: #ffffff; }
QPushButton#secondaryBtn {
    background: #ffffff; border: 1px solid #b8b8b8; color: #000000; font-weight: 500;
    border-radius: 12px; padding: 9px 16px;
}
QPushButton#secondaryBtn:hover { background: #f2f2f2; border-color: #777777; }
QPushButton#secondaryBtn:pressed { background: #e8e8e8; }
QPushButton#secondaryBtn:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }

QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QSpinBox {
    background: #ffffff; border: 1px solid #c8c8c8;
    border-radius: 10px; padding: 7px; color: #111111;
    selection-background-color: #111111; selection-color: #ffffff;
}
QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {
    border: 1px solid #111111; background: #ffffff;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #ffffff; color: #111111; border: 1px solid #c8c8c8;
    selection-background-color: #e0e0e0; border-radius: 8px;
}
QListWidget::item { padding: 7px 5px; border-radius: 8px; color: #111111; }
QListWidget::item:selected { background: #e0e0e0; color: #000000; }
QListWidget::item:hover { background: #f0f0f0; }

/* Strategy page. */
QLabel#strategyLabel { color: #000000; font-size: 16px; font-weight: 700; }
QComboBox#strategyCombo, QLineEdit#strategyInput {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 12px;
    padding: 9px 12px;
    color: #111111;
    font-size: 14px;
    font-weight: 500;
}
QComboBox#strategyCombo:hover, QLineEdit#strategyInput:hover { background: #f7f7f7; border-color: #9a9a9a; }
QListWidget#strategyList {
    background: #ffffff;
    border: 1px solid #d6d6d6;
    border-radius: 16px;
    outline: none;
    padding: 14px 22px;
    color: #000000;
    font-size: 16px;
    font-weight: 600;
}
QListWidget#strategyList::item { padding: 7px 10px; border-radius: 10px; color: #000000; }
QListWidget#strategyList::item:hover { background: #f0f0f0; }
QListWidget#strategyList::item:selected,
QListWidget#strategyList::item:selected:active,
QListWidget#strategyList::item:selected:!active {
    background: #e0e0e0;
    color: #000000;
    border: none;
    outline: none;
}
QPlainTextEdit#cmdPreview,
QPlainTextEdit#strategyDetail,
QPlainTextEdit#strategyCodeEdit,
QTextEdit#logView {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 14px;
    padding: 8px 14px 8px 10px;
    color: #111111;
    font-family: 'Cascadia Mono','Consolas','Liberation Mono',monospace;
    font-size: 16px;
}
QPlainTextEdit#cmdPreview { font-size: 14px; color: #333333; }
QPlainTextEdit, QTextEdit#logView { font-family: 'Consolas','Cascadia Mono',monospace; }
QTextEdit#logView { font-size: 12px; }
QGroupBox#strategyBox {
    background: transparent;
    border: none;
    border-radius: 18px;
    margin-top: 18px;
    padding: 18px;
    color: #000000;
    font-weight: 700;
}
QGroupBox#strategyBox::title {
    subcontrol-origin: margin;
    left: 18px;
    padding: 0 8px;
    color: #000000;
    font-weight: 700;
}
QPushButton#strategySoftBtn,
QPushButton#strategyPrimaryBtn,
QPushButton#strategyDangerBtn,
QPushButton#strategyEditorBtn {
    background: #ffffff;
    border: 1px solid #b8b8b8;
    border-radius: 13px;
    padding: 10px 18px;
    color: #000000;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#strategySoftBtn:hover,
QPushButton#strategyPrimaryBtn:hover,
QPushButton#strategyDangerBtn:hover,
QPushButton#strategyEditorBtn:hover { background: #f2f2f2; border-color: #777777; color: #000000; }
QPushButton#strategyEditorBtn:pressed { background: #e8e8e8; }

QProgressBar, QProgressBar#popupProgress {
    background: #e8e8e8; border: 1px solid #c8c8c8; border-radius: 7px;
    height: 12px; text-align: center; color: transparent;
}
QProgressBar::chunk, QProgressBar#popupProgress::chunk { background: #1a1a1a; border-radius: 7px; }

QCheckBox { spacing: 8px; padding: 3px 0; color: #000000; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #777777; background: #ffffff; }
QCheckBox::indicator:hover { background: #eeeeee; border-color: #000000; }
QCheckBox::indicator:checked { background: #000000; border: 1px solid #000000; }

/* Settings tab. */
QFrame#settingsCard { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 28px; }
QFrame#settingsRow { background: #f3f3f3; border: 1px solid #d6d6d6; border-radius: 12px; }
QFrame#settingsRow:hover { background: #eeeeee; }
QCheckBox#settingsCheck, QCheckBox#settingsThemeCheck {
    color: #000000;
    font-size: 16px;
    font-weight: 500;
    spacing: 8px;
    padding: 0;
}
QCheckBox#settingsCheck::indicator, QCheckBox#settingsThemeCheck::indicator {
    width: 21px; height: 21px; border-radius: 5px;
    border: 1px solid #777777; background: #ffffff;
}
QCheckBox#settingsCheck::indicator:hover, QCheckBox#settingsThemeCheck::indicator:hover { background: #eeeeee; border-color: #000000; }
QCheckBox#settingsCheck::indicator:checked, QCheckBox#settingsThemeCheck::indicator:checked { background: #000000; border: 1px solid #000000; }
QLabel#settingsThemeTitle { color: #000000; font-size: 15px; font-weight: 700; margin-top: 4px; }
QPushButton#settingsLangBtn {
    background: #ffffff;
    border: 1px solid #b8b8b8;
    border-radius: 14px;
    color: #000000;
    font-size: 13px;
    font-weight: 800;
    min-width: 46px; max-width: 46px;
    min-height: 28px; max-height: 28px;
    padding: 0;
}
QPushButton#settingsLangBtn:hover { background: #f2f2f2; color: #000000; border-color: #777777; }
QPushButton#settingsSoftBtn {
    background: #ffffff;
    border: 1px solid #b8b8b8;
    border-radius: 13px;
    padding: 7px 18px;
    color: #000000;
    font-size: 15px;
    font-weight: 500;
}
QPushButton#settingsSoftBtn:hover { background: #f2f2f2; border-color: #777777; }
QPushButton#settingsSoftBtn:pressed { background: #e8e8e8; }
QPushButton#settingsPrimaryBtn {
    background: #1a1a1a;
    border: 1px solid #1a1a1a;
    border-radius: 13px;
    padding: 7px 18px;
    color: #ffffff;
    font-size: 15px;
    font-weight: 500;
}
QPushButton#settingsPrimaryBtn:hover { background: #333333; border-color: #333333; color: #ffffff; }
QPushButton#settingsPrimaryBtn:pressed { background: #000000; }

/* Games & Services tab. */
QLabel#gamesTitle { color: #000000; font-size: 29px; font-weight: 650; }
QLabel#gamesSubtitle { color: #333333; font-size: 15px; font-weight: 500; }
QFrame#gamesCard { background: #ffffff; border: 1px solid #d0d0d0; border-radius: 30px; }
QFrame#gamesColumn { background: transparent; border: none; }
QWidget#gamesColumnIcon { min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px; }
QLabel#gamesColumnTitle { color: #000000; font-size: 19px; font-weight: 600; }
QCheckBox#gamesCheck { color: #000000; font-size: 22px; font-weight: 500; spacing: 8px; padding: 0; }
QCheckBox#gamesCheck::indicator {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #777777; background: #ffffff;
}
QCheckBox#gamesCheck::indicator:hover { background: #eeeeee; border-color: #000000; }
QCheckBox#gamesCheck::indicator:checked { background: #000000; border: 1px solid #000000; }
QWidget#gamesDomainBlock { background: transparent; margin-top: 0; }
QLabel#gamesDomainLabel { color: #000000; font-size: 14px; font-weight: 650; padding-left: 10px; margin-bottom: 0; }
QLineEdit#gamesInput {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    border-radius: 8px;
    padding: 3px 10px;
    color: #111111;
    font-size: 13px;
    font-weight: 500;
    min-height: 18px;
    max-height: 24px;
}
QLineEdit#gamesInput:focus { border: 1px solid #111111; background: #ffffff; }
QFrame#gamesDivider { background: #c8c8c8; border: none; min-width: 1px; max-width: 1px; }
QLabel#gamesNote {
    color: #444444;
    font-size: 13pt;
    font-weight: 500;
    margin-top: -4px;
    min-height: 30px;
    padding: 0 10px 2px 10px;
}
QGroupBox#gamesFilterBox {
    background: transparent;
    border: none;
    border-radius: 16px;
    margin-top: 0px;
    color: #000000;
    font-size: 19px;
    font-weight: 650;
}
QGroupBox#gamesFilterBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top center;
    top: -4px;
    padding: 0 8px;
    color: #000000;
    font-size: 18px;
    font-weight: 650;
}
QCheckBox#gamesFilterCheck { color: #000000; font-size: 13px; font-weight: 500; spacing: 7px; padding: 0; }
QCheckBox#gamesFilterCheck::indicator {
    width: 17px; height: 17px; border-radius: 5px;
    border: 1px solid #777777; background: #ffffff;
}
QCheckBox#gamesFilterCheck::indicator:checked { background: #000000; border-color: #000000; }
QLabel#gamesFilterWarn { color: #444444; font-size: 12px; font-weight: 500; }

QScrollArea#tabScroll { background: transparent; border: none; }
QScrollArea#tabScroll > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #c0c0c0; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #9a9a9a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #c0c0c0; border-radius: 4px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: #9a9a9a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QLabel#h1 { color: #000000; font-size: 22px; font-weight: 500; }
QLabel#subtitle { color: #444444; font-size: 13px; font-weight: 500; }
QLabel#muted { color: #555555; }
QLabel#tgFieldLabel { color: #555555; }
QLabel#gamesCardTitle { color: #000000; }
QToolTip { background: #ffffff; color: #111111; border: 1px solid #c8c8c8; padding: 6px; border-radius: 6px; }

/* --- Popup / dialog text, kept explicit so nothing falls back to white. --- */
QLabel#popupTitle, QLabel#popupBody, QLabel#popupPercent, QLabel#popupDetail { color: #000000; }
QPushButton#popupOk, QPushButton#popupCancel {
    background: #ffffff; color: #000000; border: 1px solid #b8b8b8; border-radius: 8px;
}
QPushButton#popupOk:hover, QPushButton#popupCancel:hover { background: #f2f2f2; border-color: #777777; color: #000000; }
QFrame#navPanel, QFrame#navIndicator,
QFrame#settingsCard, QFrame#gamesCard, QFrame#runBox,
QTabWidget#innerTabs::pane {
    background: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 14px;
}
QFrame#navIndicator { background: #e9e9e9; }
QPushButton#navBtn { color: #1a1a1a; background: transparent; border: none; }
QPushButton#navBtn:hover:!checked { background: #eeeeee; color: #000000; }
QPushButton#navBtn:checked { color: #000000; background: transparent; }

QPushButton#gradBtn {
    background: #ffffff;
    color: #000000;
    border: 1px solid #b8b8b8;
    border-radius: 18px;
    padding: 20px 22px 20px 18px;
    text-align: left;
    min-width: 205px;
    min-height: 64px;
    font-size: 18px;
    font-weight: 500;
}
QPushButton#gradBtn:hover { background: #f2f2f2; border-color: #8a8a8a; }
QPushButton#gradBtn:pressed { background: #e8e8e8; }
QPushButton#gradBtn:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }

QPushButton#ghostBtn,
QPushButton#settingsSoftBtn,
QPushButton#settingsPrimaryBtn,
QPushButton#settingsLangBtn,
QPushButton#strategySoftBtn,
QPushButton#strategyPrimaryBtn,
QPushButton#strategyDangerBtn,
QPushButton#strategyEditorBtn,
QPushButton#popupOk,
QPushButton#popupCancel,
QPushButton {
    background: #ffffff;
    color: #000000;
    border: 1px solid #b8b8b8;
    border-radius: 8px;
}
QPushButton:hover, QPushButton#ghostBtn:hover,
QPushButton#settingsSoftBtn:hover, QPushButton#settingsPrimaryBtn:hover,
QPushButton#settingsLangBtn:hover,
QPushButton#strategySoftBtn:hover, QPushButton#strategyPrimaryBtn:hover,
QPushButton#strategyDangerBtn:hover, QPushButton#strategyEditorBtn:hover,
QPushButton#popupOk:hover, QPushButton#popupCancel:hover {
    background: #f2f2f2;
    border-color: #777777;
    color: #000000;
}
QPushButton:pressed { background: #e8e8e8; }
QPushButton:disabled { background: #eeeeee; color: #8a8a8a; border-color: #d0d0d0; }

QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget,
QLineEdit#runField, QPlainTextEdit#cmdPreview, QPlainTextEdit#strategyDetail,
QPlainTextEdit#strategyCodeEdit, QTextEdit#logView, QTextEdit#homeLog,
QComboBox#strategyCombo, QLineEdit#strategyInput, QLineEdit#gamesInput {
    background: #ffffff;
    border: 1px solid #c8c8c8;
    color: #111111;
    selection-background-color: #111111;
    selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus,
QComboBox#strategyCombo:focus, QLineEdit#strategyInput:focus, QLineEdit#gamesInput:focus {
    border: 1px solid #111111;
    background: #ffffff;
}
QComboBox QAbstractItemView { background: #ffffff; color: #111111; selection-background-color: #e0e0e0; }
QListWidget::item:selected, QListWidget#strategyList::item:selected,
QListWidget#strategyList::item:selected:active, QListWidget#strategyList::item:selected:!active {
    background: #e0e0e0;
    color: #000000;
}
QListWidget::item:hover, QListWidget#strategyList::item:hover { background: #f0f0f0; }

QLabel#runTitle, QLabel#statusText, QLabel#strategyLabel, QLabel#settingsThemeTitle,
QLabel#gamesTitle, QLabel#gamesSubtitle, QLabel#gamesColumnTitle, QLabel#gamesDomainLabel,
QLabel#gamesNote, QLabel#gamesFilterWarn, QLabel#popupTitle, QLabel#popupBody,
QLabel#popupPercent, QLabel#popupDetail, QLabel#muted,
QCheckBox#settingsCheck, QCheckBox#settingsThemeCheck, QCheckBox#gamesCheck,
QCheckBox#gamesFilterCheck, QGroupBox#gamesFilterBox, QGroupBox#strategyBox {
    color: #000000;
}
QFrame#settingsRow { background: #f3f3f3; border: 1px solid #d6d6d6; }
QFrame#settingsRow:hover { background: #eeeeee; }
QGroupBox, QGroupBox#strategyBox, QGroupBox#gamesFilterBox { background: transparent; border-color: #d0d0d0; color: #000000; }
QGroupBox::title, QGroupBox#strategyBox::title, QGroupBox#gamesFilterBox::title { color: #000000; }

QCheckBox::indicator, QCheckBox#settingsCheck::indicator, QCheckBox#settingsThemeCheck::indicator,
QCheckBox#gamesCheck::indicator, QCheckBox#gamesFilterCheck::indicator {
    background: #ffffff;
    border: 1px solid #777777;
    border-radius: 4px;
}
QCheckBox::indicator:hover, QCheckBox#settingsCheck::indicator:hover, QCheckBox#settingsThemeCheck::indicator:hover,
QCheckBox#gamesCheck::indicator:hover, QCheckBox#gamesFilterCheck::indicator:hover {
    background: #eeeeee;
    border-color: #000000;
}
QCheckBox::indicator:checked, QCheckBox#settingsCheck::indicator:checked, QCheckBox#settingsThemeCheck::indicator:checked,
QCheckBox#gamesCheck::indicator:checked, QCheckBox#gamesFilterCheck::indicator:checked {
    background: #000000;
    border: 1px solid #000000;
}
QProgressBar, QProgressBar#popupProgress { background: #e8e8e8; border: 1px solid #c8c8c8; border-radius: 4px; color: transparent; }
QProgressBar::chunk, QProgressBar#popupProgress::chunk { background: #000000; border-radius: 4px; }
QFrame#gamesDivider { background: #c8c8c8; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: #c0c0c0; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #9a9a9a; }
QToolTip { background: #000000; color: #ffffff; border: 1px solid #000000; }

/* Explicit light-theme text fixes. */
QFrame#statusPill QLabel#statusText { color: #000000; }
QTabWidget#innerTabs QTabBar::tab {
    background: #ffffff;
    border: 1px solid #d0d0d0;
    color: #000000;
}
QTabWidget#innerTabs QTabBar::tab:selected {
    background: #e9e9e9;
    color: #000000;
}
QTabWidget#innerTabs QTabBar::tab:hover:!selected {
    background: #f2f2f2;
    color: #000000;
}
QListWidget#strategyList {
    color: #000000;
    background: #ffffff;
}
QListWidget#strategyList::item { color: #000000; }
QListWidget#strategyList::item:selected,
QListWidget#strategyList::item:selected:active,
QListWidget#strategyList::item:selected:!active {
    background: #e0e0e0;
    color: #000000;
}

"""
