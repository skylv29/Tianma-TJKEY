# styles/light.py
# TJKEY 浅色主题 QSS — 与深色主题结构完全对应
#
# 设计语言：干净白底 + 金色强调（与深色主题保持一致的强调色体系）
#   - 背景层次：#f5f5f5 → #ffffff → #fafafa
#   - 强调色：#d4900f（深金，浅色背景上比 #f5a623 更有辨识度）
#   - 主文字：#121212，次文字：#6a6a6a
#   - 按钮：与深色主题相同的胶囊语言（border-radius: 9999px）
#   - 边框：#e0e0e0 标准边框，焦点态用金色

LIGHT_QSS = """

/* 全局基础 */
QWidget {
    background-color: #f5f5f5;
    color: #121212;
    font-family: "Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Segoe UI",sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}
QMainWindow { background-color: #f5f5f5; }
QMainWindow::centralWidget { background-color: #f5f5f5; }
QStackedWidget { background-color: #f5f5f5; }

/* QLabel */
QLabel { background-color: transparent; color: #121212; padding: 0px; }
QLabel[class="title"] { font-size: 18px; font-weight: 700; color: #121212; }
QLabel[class="subtitle"] { color: #6a6a6a; font-size: 12px; }
QLabel[class="hint"] { color: #9a9a9a; font-size: 12px; }
QLabel[class="field-label"] { color: #6a6a6a; font-size: 12px; min-width: 90px; }
QLabel[class="field-value"] { color: #121212; font-size: 13px; padding: 2px 4px; }
QLabel[class="masked"] { color: #c0c0c0; letter-spacing: 3px; font-size: 14px; }
QLabel[class="section-header"] { color: #d4900f; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; padding: 8px 16px 4px 16px; }
QLabel[class="app-title"] { font-size: 24px; font-weight: 700; color: #121212; letter-spacing: 2px; }
QLabel[class="entry-name"] { font-size: 15px; font-weight: 700; color: #121212; }
QLabel[class="entry-meta"] { color: #9a9a9a; font-size: 12px; }
QLabel[class="danger"] { color: #d20f39; }
QLabel[class="success"] { color: #1a8a3a; }
QLabel[class="warning"] { color: #b06000; }

/* QLineEdit */
QLineEdit {
    background-color: #ffffff;
    color: #121212;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #d4900f;
    selection-color: #ffffff;
}
QLineEdit:hover { background-color: #fafafa; border-color: #c0c0c0; }
QLineEdit:focus { border: 2px solid #d4900f; background-color: #ffffff; padding: 7px 11px; }
QLineEdit:disabled { color: #c0c0c0; background-color: #f0f0f0; border-color: #e8e8e8; }
QLineEdit[class="search"] {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 9999px;
    padding: 8px 20px;
}
QLineEdit[class="search"]:focus { border: 2px solid #d4900f; padding: 7px 19px; }

/* QPushButton — 默认次要（胶囊） */
QPushButton {
    background-color: #ffffff;
    color: #121212;
    border: 1px solid #d0d0d0;
    border-radius: 9999px;
    padding: 7px 18px;
    font-size: 13px;
    font-weight: 600;
    min-height: 30px;
    letter-spacing: 0.5px;
}
QPushButton:hover { background-color: #f0f0f0; border-color: #b0b0b0; }
QPushButton:pressed { background-color: #e8e8e8; }
QPushButton:disabled { color: #c0c0c0; background-color: #f8f8f8; border-color: #e8e8e8; }

/* primary — 金色实心胶囊 */
QPushButton[class="primary"] {
    background-color: #d4900f;
    color: #ffffff;
    border: none;
    font-weight: 700;
    padding: 9px 32px;
    border-radius: 9999px;
    letter-spacing: 1px;
}
QPushButton[class="primary"]:hover { background-color: #e09e1a; }
QPushButton[class="primary"]:pressed { background-color: #b87a0a; }
QPushButton[class="primary"]:disabled { background-color: #d0c0a0; color: #ffffff; }

/* danger */
QPushButton[class="danger"] { background-color: transparent; color: #d20f39; border: 1px solid #d20f39; border-radius: 9999px; }
QPushButton[class="danger"]:hover { background-color: rgba(210,15,57,0.08); }
QPushButton[class="danger"]:pressed { background-color: rgba(210,15,57,0.15); }

/* ghost */
QPushButton[class="ghost"] { background-color: transparent; color: #6a6a6a; border: 1px solid #d0d0d0; border-radius: 9999px; }
QPushButton[class="ghost"]:hover { background-color: #f0f0f0; color: #121212; border-color: #b0b0b0; }

/* icon-btn — 圆形小按钮 */
QPushButton[class="icon-btn"] {
    background-color: transparent;
    color: #6a6a6a;
    border: none;
    border-radius: 9999px;
    padding: 4px 10px;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
QPushButton[class="icon-btn"]:hover { background-color: #eeeeee; color: #121212; }
QPushButton[class="icon-btn"]:pressed { background-color: #e0e0e0; }

/* theme-btn */
QPushButton[class="theme-btn"] { background-color: transparent; border: none; color: #6a6a6a; border-radius: 9999px; padding: 4px 8px; min-height: 28px; }
QPushButton[class="theme-btn"]:hover { background-color: #eeeeee; color: #121212; }

/* new-entry-btn */
QPushButton[class="new-entry-btn"] { background-color: #d4900f; color: #ffffff; border: none; border-radius: 9999px; font-weight: 700; font-size: 13px; padding: 6px 20px; letter-spacing: 0.8px; }
QPushButton[class="new-entry-btn"]:hover { background-color: #e09e1a; }
QPushButton[class="new-entry-btn"]:pressed { background-color: #b87a0a; }

/* QCheckBox */
QCheckBox { color: #121212; spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #d0d0d0; border-radius: 4px; background-color: #ffffff; }
QCheckBox::indicator:checked { background-color: #d4900f; border-color: #d4900f; }
QCheckBox::indicator:hover { border-color: #d4900f; }

/* QComboBox */
QComboBox { background-color: #ffffff; color: #121212; border: 1px solid #e0e0e0; border-radius: 8px; padding: 6px 12px; font-size: 13px; min-height: 30px; }
QComboBox:hover { background-color: #fafafa; border-color: #c0c0c0; }
QComboBox:focus { border: 2px solid #d4900f; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border: none; }
QComboBox::down-arrow { image: none; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 5px solid #6a6a6a; margin-right: 8px; }
QComboBox QAbstractItemView { background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; color: #121212; selection-background-color: #f5f5f5; outline: none; padding: 4px; }
QComboBox QAbstractItemView::item { padding: 8px 12px; min-height: 32px; border-radius: 4px; }
QComboBox QAbstractItemView::item:hover { background-color: #f0f0f0; }
QComboBox QAbstractItemView::item:selected { background-color: #f0f0f0; color: #d4900f; }

/* QScrollBar */
QScrollBar:vertical { background-color: transparent; width: 6px; border: none; margin: 0; }
QScrollBar::handle:vertical { background-color: #d8d8d8; border-radius: 3px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background-color: #b8b8b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; height: 0px; border: none; }
QScrollBar:horizontal { background-color: transparent; height: 6px; border: none; margin: 0; }
QScrollBar::handle:horizontal { background-color: #d8d8d8; border-radius: 3px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background-color: #b8b8b8; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; width: 0px; border: none; }

/* QListWidget */
QListWidget { background-color: #f5f5f5; border: none; outline: none; padding: 4px 0px; }
QListWidget::item { padding: 9px 14px; border-radius: 6px; margin: 1px 6px; color: #121212; }
QListWidget::item:hover { background-color: #eeeeee; }
QListWidget::item:selected { background-color: #e8e8e8; color: #d4900f; }

/* QTreeWidget */
QTreeWidget { background-color: #efefef; border: none; outline: none; padding: 4px 0px; show-decoration-selected: 1; }
QTreeWidget::item { padding: 7px 10px; border-radius: 6px; margin: 1px 6px; color: #6a6a6a; min-height: 30px; }
QTreeWidget::item:hover { background-color: #e5e5e5; color: #121212; }
QTreeWidget::item:selected { background-color: #e5e5e5; color: #121212; border-left: 2px solid #d4900f; }
QTreeWidget::item:selected:hover { background-color: #dcdcdc; }
QTreeWidget::branch { background-color: transparent; }
QHeaderView::section { background-color: #efefef; color: #9a9a9a; border: none; padding: 6px 12px; font-size: 11px; }

/* QSplitter */
QSplitter { background-color: #f5f5f5; }
QSplitter::handle { background-color: #e5e5e5; }
QSplitter::handle:hover { background-color: #d4900f; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

/* QGroupBox */
QGroupBox { border: 1px solid #e8e8e8; border-radius: 10px; margin-top: 14px; padding-top: 10px; color: #6a6a6a; font-size: 12px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; top: -8px; background-color: #f5f5f5; padding: 0 8px; color: #6a6a6a; }

/* QDialog */
QDialog { background-color: #ffffff; border-radius: 12px; }
QMessageBox { background-color: #ffffff; }
QMessageBox QLabel { color: #121212; }
QMessageBox QPushButton { min-width: 80px; padding: 6px 20px; }
QInputDialog { background-color: #ffffff; }
QInputDialog QLabel { color: #121212; }

/* QToolTip */
QToolTip { background-color: #ffffff; color: #121212; border: 1px solid #e0e0e0; border-radius: 6px; padding: 5px 10px; font-size: 12px; }

/* QProgressBar */
QProgressBar { background-color: #e8e8e8; border: none; border-radius: 3px; color: transparent; height: 4px; max-height: 4px; }
QProgressBar::chunk { background-color: #d4900f; border-radius: 3px; }

/* QFrame */
QFrame[class="card"] { background-color: #ffffff; border: 1px solid #eeeeee; border-radius: 10px; padding: 16px; }
QFrame[class="detail-panel"] { background-color: #f5f5f5; border-left: 1px solid #e8e8e8; }
QFrame[class="nav-panel"] { background-color: #efefef; border-right: 1px solid #e8e8e8; }
QFrame[class="list-panel"] { background-color: #f5f5f5; }
QFrame[class="separator"] { background-color: #e8e8e8; max-height: 1px; min-height: 1px; border: none; }

QFrame[class="expiry-bar-green"] { background-color: #edf7ef; border-radius: 8px; border-left: 3px solid #1a8a3a; padding: 2px 0px; }
QFrame[class="expiry-bar-yellow"] { background-color: #fff8ea; border-radius: 8px; border-left: 3px solid #b06000; padding: 2px 0px; }
QFrame[class="expiry-bar-red"] { background-color: #fdecea; border-radius: 8px; border-left: 3px solid #d20f39; padding: 2px 0px; }
QFrame[class="expiry-list"] { background-color: #ffffff; border-radius: 0px 0px 8px 8px; border: 1px solid #e8e8e8; border-top: none; padding: 4px 0px; }

QFrame[class="login-card"] { background-color: #ffffff; border: 1px solid #eeeeee; border-radius: 16px; padding: 40px; }
QFrame[class="status-bar"] { background-color: #efefef; border-top: 1px solid #e8e8e8; max-height: 44px; min-height: 44px; }
QFrame[class="title-bar"] { background-color: #efefef; border-bottom: 1px solid #e8e8e8; max-height: 52px; min-height: 52px; }

/* QScrollArea */
QScrollArea { border: none; background-color: transparent; }
QScrollArea > QWidget > QWidget { background-color: transparent; }

/* QTextEdit */
QTextEdit, QPlainTextEdit { background-color: #ffffff; color: #121212; border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; font-size: 13px; selection-background-color: #d4900f; selection-color: #ffffff; }
QTextEdit:focus, QPlainTextEdit:focus { border: 2px solid #d4900f; }

/* QMenu */
QMenu { background-color: #ffffff; border: 1px solid #e8e8e8; border-radius: 10px; padding: 6px; color: #121212; }
QMenu::item { padding: 8px 18px 8px 14px; border-radius: 6px; margin: 1px 2px; font-size: 13px; color: #121212; }
QMenu::item:selected { background-color: #f0f0f0; color: #121212; }
QMenu::item:disabled { color: #c0c0c0; }
QMenu::separator { height: 1px; background-color: #eeeeee; margin: 5px 10px; }

/* QTabWidget */
QTabWidget::pane { border: 1px solid #e8e8e8; border-radius: 0px 8px 8px 8px; background-color: #ffffff; }
QTabBar::tab { background-color: #efefef; color: #6a6a6a; border: 1px solid #e8e8e8; border-bottom: none; border-radius: 8px 8px 0px 0px; padding: 8px 18px; margin-right: 2px; font-size: 13px; font-weight: 600; }
QTabBar::tab:selected { background-color: #ffffff; color: #121212; }
QTabBar::tab:hover:!selected { background-color: #e8e8e8; color: #121212; }

/* QFileDialog */
QFileDialog { background-color: #ffffff; color: #121212; }
QFileDialog QListView, QFileDialog QTreeView { background-color: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; color: #121212; }
QFileDialog QPushButton { min-width: 80px; }
"""
