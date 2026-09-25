# ui/settings_dialog.py
# TJKEY 设置对话框
#
# 包含：
#   - 主题切换（深色/浅色）
#   - 自动锁屏时间
#   - 快捷入口：打开模板管理

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QFrame, QApplication,
)
from PySide6.QtCore import Qt

from session import session
from accounts import load_app_conf, update_app_conf
from styles import apply_theme, get_theme, DARK, LIGHT
from icons import icon as _icon, pixmap as _pixmap
from PySide6.QtCore import QSize


class SettingsDialog(QDialog):
    """
    设置对话框。
    修改立即生效，关闭时保存到 app.conf。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        # 只锁定宽度，高度交给布局自适应——固定高度会在内容增多时
        # 压缩/裁剪控件（下拉框文字只剩一半）
        self.setFixedWidth(400)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._conf = {}
        self._load_conf()
        self._build_ui()

    def _load_conf(self):
        try:
            self._conf = load_app_conf(session.myVault_path)
        except Exception:
            self._conf = {"theme": "dark", "auto_lock_minutes": 2}

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 20)
        layout.setSpacing(0)

        # 标题
        # 标题行
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        title_row = _HBox()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)
        t_icon = QLabel()
        t_icon.setPixmap(_pixmap("settings", color="#f5a623", size=20))
        t_icon.setFixedSize(20, 20)
        t_icon.setScaledContents(True)
        title_row.addWidget(t_icon)
        title = QLabel("设置")
        title.setProperty("class", "title")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)
        layout.addSpacing(20)

        # ── 外观
        layout.addWidget(self._section_label("外观"))
        layout.addWidget(self._make_row(
            "界面主题",
            self._make_theme_widget(),
        ))
        layout.addSpacing(4)

        # ── 安全
        layout.addWidget(self._section_label("安全"))
        layout.addWidget(self._make_row(
            "自动锁屏",
            self._make_lock_widget(),
        ))
        layout.addSpacing(4)
        layout.addWidget(self._make_row(
            "登录密码",
            self._make_password_widget(),
        ))
        layout.addSpacing(4)

        # ── 数据
        layout.addWidget(self._section_label("数据"))
        layout.addWidget(self._make_row(
            "条目模板",
            self._make_template_widget(),
        ))

        layout.addStretch()

        sep = QFrame()
        sep.setProperty("class", "separator")
        layout.addWidget(sep)
        layout.addSpacing(12)

        # 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setProperty("class", "primary")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "section-header")
        return lbl

    def _make_row(self, label_text: str, widget) -> QFrame:
        row = QFrame()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 8, 0, 8)
        row_layout.setSpacing(12)

        lbl = QLabel(label_text)
        lbl.setProperty("class", "field-label")
        lbl.setFixedWidth(80)
        row_layout.addWidget(lbl)
        row_layout.addWidget(widget)
        return row

    # ── 主题选择

    def _make_theme_widget(self) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumHeight(32)
        combo.addItem("  深色", DARK)
        combo.setItemIcon(combo.count()-1, _icon("moon", color="#b3b3b3", size=14))
        combo.addItem("  浅色", LIGHT)
        combo.setItemIcon(combo.count()-1, _icon("sun", color="#b3b3b3", size=14))

        current = self._conf.get("theme", DARK)
        combo.setCurrentIndex(0 if current == DARK else 1)
        combo.currentIndexChanged.connect(self._on_theme_changed)
        self._theme_combo = combo
        return combo

    def _on_theme_changed(self, idx: int):
        theme = self._theme_combo.itemData(idx)
        apply_theme(QApplication.instance(), theme)
        # 更新主窗口主题按钮图标
        parent = self.parent()
        if parent and hasattr(parent, "_update_theme_btn_icon"):
            parent._update_theme_btn_icon(theme)
        # 刷新导航按钮内联样式
        if parent and hasattr(parent, "nav_panel"):
            parent.nav_panel.refresh()
        self._save_conf(theme=theme)

    # ── 自动锁屏

    def _make_lock_widget(self) -> QComboBox:
        options = [
            ("1 分钟", 1),
            ("2 分钟（默认）", 2),
            ("5 分钟", 5),
            ("10 分钟", 10),
            ("从不", 0),
        ]
        combo = QComboBox()
        combo.setMinimumHeight(32)
        current = self._conf.get("auto_lock_minutes", 2)

        for label, val in options:
            combo.addItem(label, val)
            if val == current:
                combo.setCurrentIndex(combo.count() - 1)

        combo.currentIndexChanged.connect(self._on_lock_changed)
        self._lock_combo = combo
        return combo

    def _on_lock_changed(self, idx: int):
        minutes = self._lock_combo.itemData(idx)
        self._save_conf(auto_lock_minutes=minutes)
        # 通知主窗口更新锁屏计时器
        parent = self.parent()
        if parent and hasattr(parent, "_lock_minutes"):
            parent._lock_minutes = minutes
            parent._reset_lock_timer()

    # ── 模板管理入口

    def _make_template_widget(self) -> QPushButton:
        btn = QPushButton("管理条目模板 →")
        btn.setProperty("class", "ghost")
        btn.clicked.connect(self._open_template_manager)
        return btn

    def _open_template_manager(self):
        from ui.template_manager import TemplateManagerDialog
        dlg = TemplateManagerDialog(self)
        dlg.exec()

    # ── 修改登录密码入口

    def _make_password_widget(self) -> QPushButton:
        btn = QPushButton("修改登录密码 →")
        btn.setProperty("class", "ghost")
        btn.clicked.connect(self._open_change_password)
        return btn

    def _open_change_password(self):
        from ui.change_password_dialog import ChangePasswordDialog
        dlg = ChangePasswordDialog(self)
        dlg.exec()

    # ── 保存

    def _save_conf(self, **kwargs):
        try:
            update_app_conf(session.myVault_path, **kwargs)
        except Exception:
            pass
