# styles/dark.py
# TJKEY 深色主题 QSS — Spotify 风格极深黑 + 金色强调
DARK_QSS = """

/* 全局基础 */
QWidget {
    background-color: #121212;
    color: #ffffff;
    font-family: "Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}
QMainWindow { background-color: #121212; }
QMainWindow::centralWidget { background-color: #121212; }
QStackedWidget { background-color: #121212; }

/* QLabel */
QLabel { background-color: transparent; color: #ffffff; padding: 0px; }
QLabel[class="title"] { font-size: 18px; font-weight: 700; color: #ffffff; }
QLabel[class="subtitle"] { color: #b3b3b3; font-size: 12px; }
QLabel[class="hint"] { color: #6a6a6a; font-size: 12px; }
QLabel[class="field-label"] { color: #b3b3b3; font-size: 12px; min-width: 90px; }
QLabel[class="field-value"] { color: #ffffff; font-size: 13px; padding: 2px 4px; }
QLabel[class="masked"] { color: #4d4d4d; letter-spacing: 3px; font-size: 14px; }
QLabel[class="section-header"] { color: #f5a623; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; padding: 8px 16px 4px 16px; }
QLabel[class="app-title"] { font-size: 24px; font-weight: 700; color: #ffffff; letter-spacing: 2px; }
QLabel[class="entry-name"] { font-size: 15px; font-weight: 700; color: #ffffff; }
QLabel[class="entry-meta"] { color: #6a6a6a; font-size: 12px; }
QLabel[class="danger"] { color: #f3727f; }
QLabel[class="success"] { color: #1ed760; }
QLabel[class="warning"] { color: #ffa42b; }

/* QLineEdit */
QLineEdit {
    background-color: #1f1f1f;
    color: #ffffff;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #f5a623;
    selection-color: #121212;
}
QLineEdit:hover { background-color: #2a2a2a; border-color: #4d4d4d; }
QLineEdit:focus { border: 2px solid #f5a623; background-color: #1f1f1f; padding: 7px 11px; }
QLineEdit:disabled { color: #4d4d4d; background-color: #181818; border-color: #282828; }
QLineEdit[class="search"] {
    background-color: #1f1f1f;
    border: 1px solid #3a3a3a;
    border-radius: 9999px;
    padding: 8px 20px;
}
QLineEdit[class="search"]:focus { border: 2px solid #f5a623; padding: 7px 19px; }

/* QPushButton — 默认次要（胶囊） */
QPushButton {
    background-color: #1f1f1f;
    color: #ffffff;
    border: 1px solid #4d4d4d;
    border-radius: 9999px;
    padding: 7px 18px;
    font-size: 13px;
    font-weight: 600;
    min-height: 30px;
    letter-spacing: 0.5px;
}
QPushButton:hover { background-color: #2a2a2a; border-color: #7c7c7c; }
QPushButton:pressed { background-color: #353535; }
QPushButton:disabled { color: #4d4d4d; background-color: #181818; border-color: #2a2a2a; }

/* primary — 金色实心胶囊 */
QPushButton[class="primary"] {
    background-color: #f5a623;
    color: #121212;
    border: none;
    font-weight: 700;
    padding: 9px 32px;
    border-radius: 9999px;
    letter-spacing: 1px;
}
QPushButton[class="primary"]:hover { background-color: #f7b84e; }
QPushButton[class="primary"]:pressed { background-color: #e09615; }
QPushButton[class="primary"]:disabled { background-color: #4d4d4d; color: #2a2a2a; }

/* danger */
QPushButton[class="danger"] { background-color: transparent; color: #f3727f; border: 1px solid #f3727f; border-radius: 9999px; }
QPushButton[class="danger"]:hover { background-color: rgba(243,114,127,0.12); }
QPushButton[class="danger"]:pressed { background-color: rgba(243,114,127,0.20); }

/* ghost */
QPushButton[class="ghost"] { background-color: transparent; color: #b3b3b3; border: 1px solid #4d4d4d; border-radius: 9999px; }
QPushButton[class="ghost"]:hover { background-color: #1f1f1f; color: #ffffff; border-color: #7c7c7c; }

/* icon-btn — 圆形小按钮 */
QPushButton[class="icon-btn"] {
    background-color: transparent;
    color: #b3b3b3;
    border: none;
    border-radius: 9999px;
    padding: 4px 10px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
QPushButton[class="icon-btn"]:hover { background-color: #2a2a2a; color: #ffffff; }
QPushButton[class="icon-btn"]:pressed { background-color: #353535; }

/* theme-btn */
QPushButton[class="theme-btn"] { background-color: transparent; border: none; color: #b3b3b3; border-radius: 9999px; padding: 4px 8px; min-height: 28px; }
QPushButton[class="theme-btn"]:hover { background-color: #1f1f1f; color: #ffffff; }

/* new-entry-btn */
QPushButton[class="new-entry-btn"] { background-color: #f5a623; color: #121212; border: none; border-radius: 9999px; font-weight: 700; font-size: 13px; padding: 6px 20px; letter-spacing: 0.8px; }
QPushButton[class="new-entry-btn"]:hover { background-color: #f7b84e; }
QPushButton[class="new-entry-btn"]:pressed { background-color: #e09615; }

/* QCheckBox */
QCheckBox { color: #ffffff; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #4d4d4d; border-radius: 4px; background-color: #1f1f1f; }
QCheckBox::indicator:checked { background-color: #f5a623; border-color: #f5a623; }
QCheckBox::indicator:hover { border-color: #f5a623; }

/* QComboBox */
QComboBox { background-color: #1f1f1f; color: #ffffff; border: 1px solid #3a3a3a; border-radius: 8px; padding: 6px 12px; font-size: 13px; min-height: 30px; }
QComboBox:hover { background-color: #2a2a2a; border-color: #4d4d4d; }
QComboBox:focus { border: 2px solid #f5a623; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border: none; }
QComboBox::down-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #b3b3b3; margin-right: 8px; }
QComboBox QAbstractItemView { background-color: #282828; border: none; border-radius: 8px; color: #ffffff; selection-background-color: #3a3a3a; outline: none; padding: 4px; }
QComboBox QAbstractItemView::item { padding: 8px 12px; min-height: 32px; border-radius: 4px; }
QComboBox QAbstractItemView::item:hover { background-color: #3a3a3a; }
QComboBox QAbstractItemView::item:selected { background-color: #3a3a3a; color: #f5a623; }

/* QScrollBar */
QScrollBar:vertical { background-color: transparent; width: 6px; border: none; margin: 0; }
QScrollBar::handle:vertical { background-color: #3a3a3a; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background-color: #4d4d4d; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; height: 0px; border: none; }
QScrollBar:horizontal { background-color: transparent; height: 6px; border: none; margin: 0; }
QScrollBar::handle:horizontal { background-color: #3a3a3a; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background-color: #4d4d4d; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; width: 0px; border: none; }

/* QListWidget */
QListWidget { background-color: #121212; border: none; outline: none; padding: 4px 0px; }
QListWidget::item { padding: 9px 14px; border-radius: 6px; margin: 1px 6px; color: #ffffff; }
QListWidget::item:hover { background-color: #1f1f1f; }
QListWidget::item:selected { background-color: #2a2a2a; color: #f5a623; }

/* QTreeWidget */
QTreeWidget { background-color: #181818; border: none; outline: none; padding: 4px 0px; show-decoration-selected: 1; }
QTreeWidget::item { padding: 7px 10px; border-radius: 6px; margin: 1px 6px; color: #b3b3b3; min-height: 30px; }
QTreeWidget::item:hover { background-color: #2a2a2a; color: #ffffff; }
QTreeWidget::item:selected { background-color: #2a2a2a; color: #ffffff; border-left: 2px solid #f5a623; }
QTreeWidget::item:selected:hover { background-color: #353535; }
QTreeWidget::branch { background-color: transparent; }
QHeaderView::section { background-color: #181818; color: #6a6a6a; border: none; padding: 6px 12px; font-size: 11px; }

/* QSplitter */
QSplitter { background-color: #121212; }
QSplitter::handle { background-color: #282828; }
QSplitter::handle:hover { background-color: #f5a623; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

/* QGroupBox */
QGroupBox { border: 1px solid #2a2a2a; border-radius: 10px; margin-top: 14px; padding-top: 10px; color: #b3b3b3; font-size: 12px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; top: -8px; background-color: #121212; padding: 0 8px; color: #b3b3b3; }

/* QDialog */
QDialog { background-color: #181818; border-radius: 12px; }
QMessageBox { background-color: #181818; }
QMessageBox QLabel { color: #ffffff; }
QMessageBox QPushButton { min-width: 80px; padding: 6px 20px; }
QInputDialog { background-color: #181818; }
QInputDialog QLabel { color: #ffffff; }

/* QToolTip */
QToolTip { background-color: #282828; color: #ffffff; border: 1px solid #3a3a3a; border-radius: 6px; padding: 5px 10px; font-size: 12px; }

/* QProgressBar */
QProgressBar { background-color: #282828; border: none; border-radius: 3px; color: transparent; height: 4px; max-height: 4px; }
QProgressBar::chunk { background-color: #f5a623; border-radius: 3px; }

/* QFrame */
QFrame[class="card"] { background-color: #181818; border: none; border-radius: 10px; padding: 16px; }
QFrame[class="detail-panel"] { background-color: #121212; border-left: 1px solid #282828; }
QFrame[class="nav-panel"] { background-color: #181818; border-right: 1px solid #282828; }
QFrame[class="list-panel"] { background-color: #121212; }
QFrame[class="separator"] { background-color: #282828; max-height: 1px; min-height: 1px; border: none; }

QFrame[class="expiry-bar-green"] { background-color: #0d2b1a; border-radius: 8px; border-left: 3px solid #1ed760; padding: 2px 0px; }
QFrame[class="expiry-bar-yellow"] { background-color: #2b1f0a; border-radius: 8px; border-left: 3px solid #ffa42b; padding: 2px 0px; }
QFrame[class="expiry-bar-red"] { background-color: #2b0d0f; border-radius: 8px; border-left: 3px solid #f3727f; padding: 2px 0px; }
QFrame[class="expiry-list"] { background-color: #181818; border-radius: 0px 0px 8px 8px; border: 1px solid #282828; border-top: none; padding: 4px 0px; }

QFrame[class="login-card"] { background-color: #181818; border: none; border-radius: 16px; padding: 40px; }
QFrame[class="status-bar"] { background-color: #181818; border-top: 1px solid #282828; max-height: 44px; min-height: 44px; }
QFrame[class="title-bar"] { background-color: #181818; border-bottom: 1px solid #282828; max-height: 52px; min-height: 52px; }

/* QScrollArea */
QScrollArea { border: none; background-color: transparent; }
QScrollArea > QWidget > QWidget { background-color: transparent; }

/* QTextEdit */
QTextEdit, QPlainTextEdit { background-color: #1f1f1f; color: #ffffff; border: 1px solid #3a3a3a; border-radius: 8px; padding: 10px; font-size: 13px; selection-background-color: #f5a623; selection-color: #121212; }
QTextEdit:focus, QPlainTextEdit:focus { border: 2px solid #f5a623; }

/* QMenu */
QMenu { background-color: #282828; border: 1px solid #3a3a3a; border-radius: 10px; padding: 6px; color: #ffffff; }
QMenu::item { padding: 8px 18px 8px 14px; border-radius: 6px; margin: 1px 2px; font-size: 13px; color: #ffffff; }
QMenu::item:selected { background-color: #3a3a3a; color: #ffffff; }
QMenu::item:disabled { color: #4d4d4d; }
QMenu::separator { height: 1px; background-color: #3a3a3a; margin: 5px 10px; }

/* QTabWidget */
QTabWidget::pane { border: 1px solid #282828; border-radius: 0px 8px 8px 8px; background-color: #181818; }
QTabBar::tab { background-color: #121212; color: #b3b3b3; border: 1px solid #282828; border-bottom: none; border-radius: 8px 8px 0px 0px; padding: 8px 18px; margin-right: 2px; font-size: 13px; font-weight: 600; }
QTabBar::tab:selected { background-color: #181818; color: #ffffff; }
QTabBar::tab:hover:!selected { background-color: #1f1f1f; color: #ffffff; }

/* QFileDialog */
QFileDialog { background-color: #181818; color: #ffffff; }
QFileDialog QListView, QFileDialog QTreeView { background-color: #1f1f1f; border: none; border-radius: 6px; color: #ffffff; }
QFileDialog QPushButton { min-width: 80px; }
"""
