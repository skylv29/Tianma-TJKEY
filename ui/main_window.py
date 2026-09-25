# ui/main_window.py
# TJKEY 主窗口
#
# 三栏布局：左侧分类导航 | 中间条目列表 | 右侧详情面板
# 顶部：标题栏（账号名、锁屏、设置、导出按钮）
# 顶部提醒条：到期提醒（红/黄/绿折叠条）
# 底部：状态栏（新建条目、主题切换、条目计数）
#
# 自动锁屏：监听全局鼠标/键盘事件，无操作 N 分钟后锁屏

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSplitter,
    QApplication, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QSize

from session import session
from accounts import load_app_conf, update_app_conf
from vault_io import scan_expiry, get_expiry_level, save_vault, count_active_entries
from styles import apply_theme, get_theme, DARK, LIGHT, color
from icons import icon as _icon, pixmap as _pixmap, expiry_dot, dark_icon


class MainWindow(QMainWindow):
    """
    TJKEY 主窗口。

    发射的信号：
        lock_requested()  请求回到登录界面
    """
    lock_requested = Signal()

    def __init__(self):
        super().__init__()
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._do_lock)

        self._lock_minutes = 2          # 默认 2 分钟，从 app.conf 读取
        self._expiry_expanded = False   # 到期提醒是否展开

        self._build_ui()
        self._load_conf()

        # 安装全局事件过滤器（监听鼠标/键盘重置计时器）
        QApplication.instance().installEventFilter(self)

        # 系统锁屏联动：Windows 会话被锁定（Win+L 等）时立即锁屏。
        # _do_lock 内置已锁屏守卫，重复触发无副作用。
        from system_lock import SystemLockWatcher
        self._system_lock_watcher = SystemLockWatcher(self)
        self._system_lock_watcher.locked.connect(self._do_lock)
        self._system_lock_watcher.start()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────

    def _build_ui(self):
        self.setWindowTitle("TJKEY")
        self.setMinimumSize(900, 600)
        # 窗口图标
        self._apply_window_icon()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部标题栏
        root.addWidget(self._make_title_bar())

        # ── 到期提醒折叠条
        self.expiry_frame = self._make_expiry_bar()
        root.addWidget(self.expiry_frame)

        # ── 主体三栏
        root.addWidget(self._make_body(), stretch=1)

        # ── 底部状态栏
        root.addWidget(self._make_status_bar())

    # ── 标题栏

    def _make_title_bar(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("class", "title-bar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(8)

        # 左侧：logo + 账号名
        logo = QLabel()
        logo.setPixmap(_pixmap("lock", color="#f5a623", size=20))
        logo.setFixedSize(20, 20)
        logo.setScaledContents(True)
        layout.addWidget(logo)

        self.account_lbl = QLabel("TJKEY")
        self.account_lbl.setProperty("class", "title")
        layout.addWidget(self.account_lbl)

        layout.addStretch()

        # 右侧按钮组
        self.lock_btn     = self._make_bar_btn("lock",     "锁屏",   self._do_lock)
        self.export_btn   = self._make_bar_btn("upload",   "导出",   self._do_export)
        self.settings_btn = self._make_bar_btn("settings", "设置",   self._do_settings)

        layout.addWidget(self.lock_btn)
        layout.addWidget(self.export_btn)
        layout.addWidget(self.settings_btn)

        return bar

    def _make_bar_btn(self, icon_name: str, text: str, slot) -> QPushButton:
        btn = QPushButton(f"  {text}")
        btn.setProperty("class", "icon-btn")
        btn.setFixedHeight(30)
        btn.setIcon(_icon(icon_name, color="#b3b3b3", size=15))
        btn.setIconSize(QSize(15, 15))
        btn.clicked.connect(slot)
        return btn

    # ── 到期提醒折叠条

    def _make_expiry_bar(self) -> QFrame:
        container = QFrame()
        container.setProperty("class", "expiry-bar-green")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 折叠头
        header = QFrame()
        header.setObjectName("expiry_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        self.expiry_icon_lbl = QLabel()
        self.expiry_icon_lbl.setPixmap(expiry_dot("green", size=12))
        self.expiry_icon_lbl.setFixedSize(12, 12)
        self.expiry_icon_lbl.setScaledContents(True)
        header_layout.addWidget(self.expiry_icon_lbl)

        self.expiry_text_lbl = QLabel("到期提醒：所有项目均在 3 个月以外")
        self.expiry_text_lbl.setProperty("class", "hint")
        header_layout.addWidget(self.expiry_text_lbl)

        header_layout.addStretch()

        self.expiry_toggle_btn = QPushButton("▼")
        self.expiry_toggle_btn.setProperty("class", "icon-btn")
        self.expiry_toggle_btn.setFixedSize(28, 28)
        self.expiry_toggle_btn.clicked.connect(self._toggle_expiry)
        header_layout.addWidget(self.expiry_toggle_btn)

        container_layout.addWidget(header)

        # 展开内容区（默认隐藏）
        self.expiry_detail = QFrame()
        self.expiry_detail.setProperty("class", "expiry-list")
        self.expiry_detail_layout = QVBoxLayout(self.expiry_detail)
        self.expiry_detail_layout.setContentsMargins(12, 6, 12, 6)
        self.expiry_detail_layout.setSpacing(4)
        self.expiry_detail.setVisible(False)
        container_layout.addWidget(self.expiry_detail)

        # 整个折叠条可点击切换
        header.setCursor(Qt.PointingHandCursor)
        header.mousePressEvent = lambda e: self._toggle_expiry()

        return container

    # ── 主体三栏

    def _make_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)

        # 左侧：分类导航
        from ui.nav_panel import NavPanel
        self.nav_panel = NavPanel()
        self.nav_panel.category_selected.connect(self._on_category_selected)
        self.nav_panel.categories_changed.connect(self._on_categories_changed)
        splitter.addWidget(self.nav_panel)

        # 中间：条目列表
        from ui.entry_list import EntryListPanel
        self.list_panel = EntryListPanel()
        self.list_panel.setMinimumWidth(240)
        self.list_panel.entry_selected.connect(self._on_entry_selected)
        self.list_panel.entry_deleted.connect(self._on_entry_deleted)
        self.list_panel.new_entry_requested.connect(self._on_new_entry_requested)
        splitter.addWidget(self.list_panel)

        # 右侧：详情/编辑面板（用 QStackedWidget 切换）
        from PySide6.QtWidgets import QStackedWidget
        from ui.entry_detail import EntryDetailPanel
        from ui.entry_edit import EntryEditPanel

        self.right_stack = QStackedWidget()
        self.right_stack.setMinimumWidth(300)

        self.detail_panel = EntryDetailPanel()
        self.detail_panel.edit_requested.connect(self._on_edit_requested)
        self.detail_panel.entry_deleted.connect(self._on_detail_entry_deleted)

        self.edit_panel = EntryEditPanel()
        self.edit_panel.save_done.connect(self._on_edit_save_done)
        self.edit_panel.cancel_requested.connect(self._on_edit_cancelled)
        self.edit_panel.entry_deleted.connect(self._on_edit_entry_deleted)

        self.right_stack.addWidget(self.detail_panel)   # index 0 = 查看
        self.right_stack.addWidget(self.edit_panel)     # index 1 = 编辑
        self.right_stack.setCurrentIndex(0)

        splitter.addWidget(self.right_stack)

        # 三栏比例 20:35:45
        splitter.setStretchFactor(0, 20)
        splitter.setStretchFactor(1, 35)
        splitter.setStretchFactor(2, 45)

        self.splitter = splitter
        return splitter

    # ── 状态栏

    def _make_status_bar(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("class", "status-bar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # 新建条目
        self.new_entry_btn = QPushButton("  新建条目")
        self.new_entry_btn.setProperty("class", "new-entry-btn")
        self.new_entry_btn.setFixedHeight(28)
        self.new_entry_btn.setIcon(dark_icon("plus", size=14))
        self.new_entry_btn.setIconSize(QSize(14, 14))
        self.new_entry_btn.clicked.connect(self._do_new_entry)
        layout.addWidget(self.new_entry_btn)

        layout.addStretch()

        # 条目计数
        self.count_lbl = QLabel("共 0 条记录")
        self.count_lbl.setProperty("class", "hint")
        layout.addWidget(self.count_lbl)

        layout.addSpacing(12)

        # 主题切换
        self.theme_btn = QPushButton()
        self.theme_btn.setProperty("class", "theme-btn")
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.setToolTip("切换主题")
        self.theme_btn.setIcon(_icon("sun", color="#b3b3b3", size=16))
        self.theme_btn.setIconSize(QSize(16, 16))
        self.theme_btn.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_btn)

        return bar

    # ─────────────────────────────────────────
    # 初始化与数据加载
    # ─────────────────────────────────────────

    def _load_conf(self):
        """从 app.conf 加载设置，并初始化 UI 状态。"""
        try:
            conf = load_app_conf(session.myVault_path)
        except Exception:
            conf = {}

        self._lock_minutes = conf.get("auto_lock_minutes", 2)

        # 恢复窗口几何
        geo = conf.get("window_geometry", {})
        w = geo.get("width", 1100)
        h = geo.get("height", 720)
        x = geo.get("x", 100)
        y = geo.get("y", 100)
        self.resize(w, h)
        self.move(x, y)

        # 主题按钮图标
        theme = conf.get("theme", DARK)
        self._update_theme_btn_icon(theme)

    def _apply_window_icon(self):
        """设置主窗口图标（ICO 优先，回退 PNG）。"""
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ico_path = os.path.join(app_dir, "assets", "icon.ico")
        png_path = os.path.join(app_dir, "assets", "icon.png")
        from PySide6.QtGui import QIcon
        if os.path.isfile(ico_path):
            self.setWindowIcon(QIcon(ico_path))
        elif os.path.isfile(png_path):
            self.setWindowIcon(QIcon(png_path))

    def on_login(self):
        """
        登录完成后由 main.py 调用，加载数据并刷新所有面板。
        """
        # 清空上一会话的残留：详情/编辑面板可能持有已显示或已解密的明文，
        # 锁屏或换账号登录后不得继续展示
        self.detail_panel.clear()
        self.edit_panel.clear()
        self.list_panel.clear_selection()
        self.right_stack.setCurrentIndex(0)   # 回到查看模式

        # 更新标题
        display = session.current_display_name or session.current_account
        self.account_lbl.setText(f"TJKEY  —  {display}")

        # 刷新导航
        self.nav_panel.refresh()
        self.nav_panel.select_all()

        # 刷新到期提醒
        self.refresh_expiry()

        # 刷新条目计数
        self.refresh_count()

        # 启动自动锁屏
        self._reset_lock_timer()

    def refresh_expiry(self):
        """扫描所有到期字段，更新顶部折叠条。"""
        if not session.vault_data:
            return

        expiry_list = scan_expiry(session.vault_data)
        level = get_expiry_level(expiry_list)

        # 更新折叠条颜色 class
        class_map = {
            "green":  "expiry-bar-green",
            "yellow": "expiry-bar-yellow",
            "red":    "expiry-bar-red",
        }
        self.expiry_frame.setProperty("class", class_map[level])
        self.expiry_frame.style().unpolish(self.expiry_frame)
        self.expiry_frame.style().polish(self.expiry_frame)

        self.expiry_icon_lbl.setPixmap(expiry_dot(level, size=12))

        # 更新文字
        if not expiry_list:
            self.expiry_text_lbl.setText("到期提醒：没有任何到期记录")
        else:
            red_cnt    = sum(1 for i in expiry_list if i["level"] == "red")
            yellow_cnt = sum(1 for i in expiry_list if i["level"] == "yellow")
            if red_cnt:
                self.expiry_text_lbl.setText(
                    f"到期提醒：有 {red_cnt} 项将在 1 个月内到期")
            elif yellow_cnt:
                self.expiry_text_lbl.setText(
                    f"到期提醒：有 {yellow_cnt} 项将在 3 个月内到期")
            else:
                self.expiry_text_lbl.setText("到期提醒：所有项目均在 3 个月以外")

        # 刷新展开内容
        self._build_expiry_detail(expiry_list)

    def _build_expiry_detail(self, expiry_list: list):
        """重建到期提醒展开区域的内容。"""
        # 清空旧内容
        while self.expiry_detail_layout.count():
            item = self.expiry_detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not expiry_list:
            lbl = QLabel("  暂无到期记录")
            lbl.setProperty("class", "hint")
            self.expiry_detail_layout.addWidget(lbl)
            return

        for item in expiry_list:
            row = QHBoxLayout()
            row.setSpacing(8)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(expiry_dot(item["level"], size=11))
            icon_lbl.setFixedSize(11, 11)
            icon_lbl.setScaledContents(True)
            row.addWidget(icon_lbl)

            # 条目名 + 字段说明
            domain_part = f"（{item['domain']}）" if item["domain"] else ""
            field_text = f"{item['entry_name']}  ·  {item['field_label']}{domain_part}"
            name_lbl = QLabel(field_text)
            name_lbl.setProperty("class", "field-value")

            # 点击跳转到该条目
            entry_id = item["entry_id"]
            name_lbl.setCursor(Qt.PointingHandCursor)
            name_lbl.mousePressEvent = (
                lambda e, eid=entry_id: self._jump_to_entry(eid)
            )
            row.addWidget(name_lbl, stretch=1)

            # 剩余天数
            days = item["days_left"]
            if days < 0:
                days_text = f"已过期 {abs(days)} 天"
            elif days == 0:
                days_text = "今天到期！"
            else:
                days_text = f"还有 {days} 天"

            days_lbl = QLabel(days_text)
            days_lbl.setProperty(
                "class",
                "danger" if item["level"] == "red" else
                "warning" if item["level"] == "yellow" else "success"
            )
            days_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            days_lbl.setFixedWidth(90)
            row.addWidget(days_lbl)

            row_widget = QWidget()
            row_widget.setLayout(row)
            self.expiry_detail_layout.addWidget(row_widget)

    def _toggle_expiry(self):
        self._expiry_expanded = not self._expiry_expanded
        self.expiry_detail.setVisible(self._expiry_expanded)
        self.expiry_toggle_btn.setText("▲" if self._expiry_expanded else "▼")

    def _jump_to_entry(self, entry_id: str):
        """跳转到指定条目：折叠提醒条，列表面板滚动并选中。"""
        self._expiry_expanded = False
        self.expiry_detail.setVisible(False)
        self.expiry_toggle_btn.setText("▼")
        # 切换到所有条目视图，再选中目标条目
        self.nav_panel.select_all()
        self.list_panel.load_category("__all__", None)
        self.list_panel.select_entry(entry_id)
        self.detail_panel.load_entry(entry_id)

    def refresh_count(self):
        """更新底部状态栏的条目计数（不含回收站中的条目）。"""
        if not session.vault_data:
            self.count_lbl.setText("共 0 条记录")
            return
        n = count_active_entries(session.vault_data)
        self.count_lbl.setText(f"共 {n} 条记录")

    # ─────────────────────────────────────────
    # 分类选择事件
    # ─────────────────────────────────────────

    def _on_category_selected(self, cat_id: str, sub_id):
        """左侧导航选中分类时，通知中间列表面板刷新。"""
        self.list_panel.load_category(cat_id, sub_id)

    def _on_categories_changed(self):
        """分类结构变化时，通知列表面板刷新（分类名称可能改变）。"""
        self.list_panel.refresh()
        self.refresh_count()

    def _on_entry_selected(self, entry_id: str):
        """条目被点击，通知详情面板显示。"""
        self.detail_panel.load_entry(entry_id)

    def _on_entry_deleted(self, entry_id: str):
        """条目被删除，刷新统计。"""
        if self.detail_panel.current_entry_id == entry_id:
            self.detail_panel.clear()
        self.list_panel.refresh()
        self.notify_entry_changed()

    def _on_detail_entry_deleted(self, entry_id: str):
        """详情面板删除条目。"""
        self.detail_panel.clear()
        self.list_panel.refresh()
        self.notify_entry_changed()

    def _on_edit_save_done(self, entry_id: str):
        """编辑/新建保存完成：切回查看模式，刷新列表和详情。"""
        self.right_stack.setCurrentIndex(0)
        self.list_panel.refresh()
        self.list_panel.select_entry(entry_id)
        self.detail_panel.load_entry(entry_id)
        self.notify_entry_changed()

    def _on_edit_cancelled(self):
        """编辑取消：切回查看模式。"""
        self.right_stack.setCurrentIndex(0)

    def _on_edit_entry_deleted(self, entry_id: str):
        """编辑面板删除条目：切回查看模式，清空详情，刷新列表。"""
        self.right_stack.setCurrentIndex(0)
        self.detail_panel.clear()
        self.list_panel.refresh()
        self.notify_entry_changed()

    def _on_edit_requested(self, entry_id: str):
        """用户点击编辑按钮，切换到编辑面板。"""
        self.edit_panel.load_edit_entry(entry_id)
        self.right_stack.setCurrentIndex(1)

    def _on_new_entry_requested(self, tpl_id: str, cat_id, sub_id):
        """新建条目请求：切换到编辑面板进行新建。"""
        self.edit_panel.load_new_entry(tpl_id, cat_id, sub_id)
        self.right_stack.setCurrentIndex(1)

    # ─────────────────────────────────────────
    # 顶部按钮动作
    # ─────────────────────────────────────────

    def _do_lock(self):
        """手动锁屏：停止计时器，清除 session，回到登录界面。"""
        self._lock_timer.stop()
        # 已锁屏时（登录界面显示中）直接返回：全局事件过滤器在登录界面
        # 也会触发本方法，若继续执行会再次发射 lock_requested，
        # 在旧登录窗口之上叠加新的登录窗口
        if session.is_locked():
            return
        self._save_window_geometry()
        # 终止进行中的导出：后台线程持有 session_key 副本，
        # 不取消的话锁屏后仍会把明文文件写完
        from ui.export_dialog import cancel_active_exports
        cancel_active_exports()
        # 清空面板中可能残留的明文（详情面板已显示的内容、编辑面板已解密的字段）
        self.detail_panel.clear()
        self.edit_panel.clear()
        self.list_panel.clear_selection()
        # 兜底清空本程序写入剪贴板的密码（30 秒自动清空在退出后不再触发）
        from ui.entry_detail import clear_app_clipboard
        clear_app_clipboard()
        session.lock()
        self.lock_requested.emit()

    def _do_export(self):
        """导出：Part 10 接入，此处占位。"""
        from ui.export_dialog import ExportDialog
        dlg = ExportDialog(self)
        dlg.exec()

    def _do_settings(self):
        """设置：Part 10 接入，此处占位。"""
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        if dlg.exec():
            # 重新加载锁屏时间
            try:
                conf = load_app_conf(session.myVault_path)
                self._lock_minutes = conf.get("auto_lock_minutes", 2)
                self._reset_lock_timer()
            except Exception:
                pass

    def _do_new_entry(self):
        """新建条目：触发模板选择弹窗。"""
        self.list_panel.show_new_entry_dialog()

    # ─────────────────────────────────────────
    # 主题切换
    # ─────────────────────────────────────────

    def _toggle_theme(self):
        current = get_theme()
        new_theme = LIGHT if current == DARK else DARK
        apply_theme(QApplication.instance(), new_theme)

        # 更新按钮图标
        self._update_theme_btn_icon(new_theme)

        # 刷新固定导航按钮的内联样式（它们用了 color() 函数）
        self.nav_panel.refresh()

        # 保存偏好
        try:
            update_app_conf(session.myVault_path, theme=new_theme)
        except Exception:
            pass

    def _update_theme_btn_icon(self, theme: str):
        """根据当前主题更新主题切换按钮的图标。"""
        # 深色模式显示太阳（点击切换到浅色），浅色模式显示月亮
        icon_name = "sun" if theme == DARK else "moon"
        self.theme_btn.setIcon(_icon(icon_name, color="#b3b3b3", size=16))
        self.theme_btn.setIconSize(QSize(16, 16))
        self.theme_btn.setText("")

    # ─────────────────────────────────────────
    # 自动锁屏
    # ─────────────────────────────────────────

    def _reset_lock_timer(self):
        """重置自动锁屏计时器。

        已锁屏时不启动：登录界面上的鼠标/键盘事件同样会经过全局事件
        过滤器到达这里，若在锁屏状态启动计时器，到期后会再次触发锁屏。
        """
        if session.is_locked() or self._lock_minutes <= 0:
            self._lock_timer.stop()
            return
        self._lock_timer.start(self._lock_minutes * 60 * 1000)

    def eventFilter(self, obj, event):
        """
        全局事件过滤器：监听鼠标移动、点击、键盘按键，
        任意交互都重置锁屏计时器。
        """
        if event.type() in (
            QEvent.MouseMove,
            QEvent.MouseButtonPress,
            QEvent.KeyPress,
            QEvent.Wheel,
        ):
            self._reset_lock_timer()
        return super().eventFilter(obj, event)

    # ─────────────────────────────────────────
    # 窗口事件
    # ─────────────────────────────────────────

    def closeEvent(self, event):
        """窗口关闭时：确认未保存编辑 → 终止导出 → 清理明文 → 锁定 session。"""
        # 编辑面板有未保存修改时先确认，避免静默丢弃用户成果
        if self.right_stack.currentIndex() == 1:
            reply = QMessageBox.question(
                self, "未保存的修改",
                "编辑面板中有未保存的修改，关闭程序将丢弃这些修改。\n\n"
                "确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        self._lock_timer.stop()
        self._system_lock_watcher.stop()
        self._save_window_geometry()
        # 终止进行中的导出，防止锁屏后线程继续写出明文文件
        from ui.export_dialog import cancel_active_exports
        cancel_active_exports()
        from ui.entry_detail import clear_app_clipboard
        clear_app_clipboard()
        session.lock()
        QApplication.instance().removeEventFilter(self)
        event.accept()

    def _save_window_geometry(self):
        """将窗口位置和大小保存到 app.conf。"""
        # 层次说明：本守卫在调用方提前短路（窗口关闭路径不进入
        # accounts 层）；accounts.save_app_conf/update_app_conf 另有
        # 入口级 ValueError 守卫兜底。两层职责不同、都保留——
        # 这里避免无谓的 load/异常路径，那里保证任何调用方都无法
        # 把 app.conf 写到相对路径（--smoke 下即 dist/）。
        # os.path.join("", "app.conf") 是相对路径，会写到进程 cwd。
        if not session.myVault_path:
            return
        try:
            geo = self.geometry()
            update_app_conf(
                session.myVault_path,
                window_geometry={
                    "width":  geo.width(),
                    "height": geo.height(),
                    "x":      geo.x(),
                    "y":      geo.y(),
                }
            )
        except Exception:
            pass

    # ─────────────────────────────────────────
    # 供外部模块调用的刷新接口
    # ─────────────────────────────────────────

    def notify_entry_changed(self):
        """
        条目增删改后调用，刷新计数和到期提醒。
        Part 7/8/9 完成后由对应面板调用。
        """
        self.refresh_expiry()
        self.refresh_count()

    def set_list_panel(self, panel: QWidget):
        """
        替换占位列表面板（Part 7 接入时调用）。
        """
        old = self.splitter.widget(1)
        self.splitter.replaceWidget(1, panel)
        self.list_panel = panel
        if old:
            old.deleteLater()

    def set_detail_panel(self, panel: QWidget):
        """
        替换占位详情面板（Part 8 接入时调用）。
        """
        old = self.splitter.widget(2)
        self.splitter.replaceWidget(2, panel)
        self.detail_panel = panel
        if old:
            old.deleteLater()


# ─────────────────────────────────────────────
# 临时占位面板（Part 7/8/9 替换）
# ─────────────────────────────────────────────

class _PlaceholderPanel(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl = QLabel(text)
        lbl.setProperty("class", "hint")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)


# ─────────────────────────────────────────────
# 独立运行预览
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    from styles import apply_theme
    apply_theme(app, "dark")

    # 建立测试 session
    tmpdir = tempfile.mkdtemp()
    vaults_dir = os.path.join(tmpdir, "vaults")
    os.makedirs(vaults_dir)

    from accounts import create_account
    from vault_io import (
        create_empty_vault, add_category, add_subcategory,
        add_entry, build_entry_from_template, save_vault,
    )
    from crypto import derive_key, encrypt_field as ef, build_field_aad

    # 使用环境变量提供测试凭据，避免向 stdout 打印真实样例密码
    create_account(tmpdir, "main", "大号",
                   os.environ.get("TJKEY_PREVIEW_PWD", "test123"),
                   os.environ.get("TJKEY_PREVIEW_EXPORT_PWD", "exp456"))
    vault_path = os.path.join(tmpdir, "vaults", "main.vault")
    vdata = create_empty_vault(vault_path, "main")

    # 填入测试数据
    cat = add_category(vdata, "域名注册")
    sub = add_subcategory(vdata, cat["id"], "Cloudflare")

    key = derive_key("test123", vdata["kdf_params"]["salt"])

    entry = build_entry_from_template("tpl_builtin_002", vdata)
    entry["name"] = "Cloudflare 主号"
    entry["category_id"] = cat["id"]
    entry["subcategory_id"] = sub["id"]
    entry["fields"][0]["value"] = "admin@gmail.com"
    entry["fields"][1]["value"] = ef(
        "SecretPass!", key,
        aad=build_field_aad(entry["id"], entry["fields"][1]["id"]))
    entry["fields"][2]["value"] = "example.com|2025-07-15"
    add_entry(vdata, entry)

    save_vault(vault_path, vdata)

    session.myVault_path = tmpdir
    session.current_account = "main"
    session.current_display_name = "大号"
    session.vault_path = vault_path
    session.vault_data = vdata
    session.session_key = key

    print(f"测试环境：{tmpdir}")

    win = MainWindow()
    win.on_login()
    win.show()

    sys.exit(app.exec())
