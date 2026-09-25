# ui/entry_detail.py
# TJKEY 右侧详情面板（查看模式）
#
# 功能：
#   - 展示条目所有字段（text/date/date_domain 直接显示，secret 默认打码）
#   - secret 字段提供 [显示] / [复制] 按钮
#   - 右上角 [编辑] 按钮切换到编辑模式（发射 edit_requested 信号）
#   - 空状态：未选中条目时显示提示
#
# 查看模式下所有字段均只读，无法直接点击修改。

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QHBoxLayout, QSizePolicy, QApplication,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from icons import icon as _icon, pixmap as _pixmap

from session import session
from vault_io import (
    get_entry_by_id, get_category_by_id,
    get_subcategory_by_id,
)
from crypto import decrypt_field, DecryptError, field_aad

# 复制的字段值在剪贴板中的保留时长（秒），到期自动清空
CLIPBOARD_CLEAR_SECONDS = 30

# 本程序最近一次写入剪贴板的值（锁屏/退出时兜底清空用）
_last_app_clipboard: str | None = None


def _clear_clipboard_if_matches(expected: str) -> None:
    """剪贴板内容仍为 expected 时清空剪贴板。

    必须是模块级函数而不能是 _FieldRow 的方法：清空定时器到触发时，
    字段行可能已被销毁（切换条目/锁屏），回调不得依赖任何控件实例。
    """
    clipboard = QApplication.clipboard()
    if clipboard.text() == expected:
        clipboard.clear()


def note_clipboard_copy(text: str) -> None:
    """记录本程序写入剪贴板的值，供锁屏/退出时匹配清空。"""
    global _last_app_clipboard
    _last_app_clipboard = text


def clear_app_clipboard() -> None:
    """锁屏/退出时清空本程序写入且未被用户覆盖的剪贴板内容。

    30 秒自动清空定时器在进程退出后不会再触发，
    这里提供锁屏与关窗路径上的兜底。
    """
    global _last_app_clipboard
    if _last_app_clipboard is not None:
        _clear_clipboard_if_matches(_last_app_clipboard)
        _last_app_clipboard = None


# ─────────────────────────────────────────────
# 详情面板主体
# ─────────────────────────────────────────────

class EntryDetailPanel(QFrame):
    """
    右侧详情面板（查看模式）。

    发射信号：
        edit_requested(entry_id)   用户点击 [编辑]，由 main_window 切换到编辑模式
        entry_deleted(entry_id)    用户在详情面板删除条目
    """
    edit_requested = Signal(str)    # entry_id
    entry_deleted  = Signal(str)    # entry_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "detail-panel")
        self.setMinimumWidth(300)

        self._current_entry_id: str | None = None
        self._field_rows: list = []   # 保存所有 _FieldRow 实例，用于批量隐藏

        self._build_ui()
        self._show_empty()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 空状态提示（未选中条目时显示）
        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_lbl = QLabel("← 从左侧选择一个条目\n\n或点击底部「+ 新建条目」")
        empty_lbl.setProperty("class", "hint")
        empty_lbl.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_lbl)
        root.addWidget(self.empty_widget)

        # ── 详情内容区
        self.content_widget = QWidget()
        self.content_widget.setVisible(False)
        content_root = QVBoxLayout(self.content_widget)
        content_root.setContentsMargins(0, 0, 0, 0)
        content_root.setSpacing(0)

        # 顶部标题栏（条目名 + 编辑按钮）
        self.header_frame = QFrame()
        self.header_frame.setFixedHeight(52)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(24, 10, 20, 10)
        header_layout.setSpacing(8)

        self.entry_name_lbl = QLabel("")
        self.entry_name_lbl.setProperty("class", "entry-name")
        self.entry_name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_layout.addWidget(self.entry_name_lbl)

        self.edit_btn = QPushButton("  编辑")
        self.edit_btn.setProperty("class", "icon-btn")
        self.edit_btn.setFixedHeight(30)
        self.edit_btn.setIcon(_icon("edit", color="#b3b3b3", size=14))
        self.edit_btn.setIconSize(QSize(14, 14))
        self.edit_btn.clicked.connect(self._do_edit)
        header_layout.addWidget(self.edit_btn)

        content_root.addWidget(self.header_frame)

        # 分类路径 + 标签行
        self.meta_frame = QFrame()
        meta_layout = QHBoxLayout(self.meta_frame)
        meta_layout.setContentsMargins(24, 0, 20, 10)
        meta_layout.setSpacing(6)

        self.cat_path_lbl = QLabel("")
        self.cat_path_lbl.setProperty("class", "entry-meta")
        meta_layout.addWidget(self.cat_path_lbl)

        meta_layout.addStretch()

        self.tags_widget = QWidget()
        self.tags_layout = QHBoxLayout(self.tags_widget)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        meta_layout.addWidget(self.tags_widget)

        content_root.addWidget(self.meta_frame)

        # 顶部分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        content_root.addWidget(sep)

        # 可滚动字段区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self.fields_container = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(24, 16, 20, 24)
        self.fields_layout.setSpacing(2)
        self.fields_layout.addStretch()

        scroll.setWidget(self.fields_container)
        content_root.addWidget(scroll, stretch=1)

        # URL 快捷行（有 URL 时显示）
        self.url_frame = QFrame()
        self.url_frame.setVisible(False)
        url_layout = QHBoxLayout(self.url_frame)
        url_layout.setContentsMargins(24, 8, 20, 10)

        url_icon = QLabel()
        url_icon.setPixmap(_pixmap("external-link", color="#6a6a6a", size=14))
        url_icon.setFixedSize(14, 14)
        url_icon.setScaledContents(True)
        url_layout.addWidget(url_icon)

        self.url_lbl = QLabel("")
        self.url_lbl.setProperty("class", "hint")
        self.url_lbl.setCursor(Qt.PointingHandCursor)
        self.url_lbl.mousePressEvent = lambda e: self._open_url()
        url_layout.addWidget(self.url_lbl, stretch=1)

        url_copy_btn = QPushButton()
        url_copy_btn.setProperty("class", "icon-btn")
        url_copy_btn.setFixedSize(28, 26)
        url_copy_btn.setIcon(_icon("copy", color="#b3b3b3", size=13))
        url_copy_btn.setIconSize(QSize(13, 13))
        url_copy_btn.setToolTip("复制网址")
        url_copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self.url_lbl.text())
        )
        url_layout.addWidget(url_copy_btn)

        content_root.addWidget(self.url_frame)

        root.addWidget(self.content_widget)

    # ─────────────────────────────────────────
    # 加载条目
    # ─────────────────────────────────────────

    def load_entry(self, entry_id: str):
        """
        加载并显示指定条目的详情。

        参数：
            entry_id - 条目 ID
        """
        if not session.vault_data:
            return

        entry = get_entry_by_id(session.vault_data, entry_id)
        if entry is None:
            self._show_empty()
            return

        self._current_entry_id = entry_id
        self._field_rows = []

        # 更新标题
        self.entry_name_lbl.setText(entry.get("name", "（未命名）"))

        # 更新分类路径
        self.cat_path_lbl.setText(self._make_cat_path(entry))

        # 更新标签
        self._render_tags(entry.get("tags", []))

        # 更新 URL
        url = entry.get("url", "")
        if url:
            self.url_lbl.setText(url)
            self.url_frame.setVisible(True)
        else:
            self.url_frame.setVisible(False)

        # 重建字段列表
        self._render_fields(entry.get("fields", []))

        # 显示内容区
        self._show_content()

    def _make_cat_path(self, entry: dict) -> str:
        """生成分类路径字符串，如"域名注册 › Cloudflare"。"""
        cat_id = entry.get("category_id")
        sub_id = entry.get("subcategory_id")
        if not cat_id or not session.vault_data:
            return "未分类"
        cat = get_category_by_id(session.vault_data, cat_id)
        if not cat:
            return "未分类"
        cat_name = cat["name"]
        if sub_id:
            _, sub = get_subcategory_by_id(session.vault_data, sub_id)
            if sub:
                return f"{cat_name}  ›  {sub['name']}"
        return cat_name

    def _render_tags(self, tags: list):
        """重建标签行。"""
        # 清空旧标签
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for tag in tags[:6]:   # 最多显示 6 个标签
            lbl = QLabel(f"#{tag}")
            from styles import color as _sc, get_theme
            _t = get_theme()
            _tag_bg  = _sc("tag_bg",  _t)
            _tag_fg  = _sc("tag_text", _t)
            lbl.setStyleSheet(
                f"QLabel {{ background-color: {_tag_bg}; "
                f"color: {_tag_fg}; border-radius: 9999px; "
                "padding: 2px 10px; font-size: 11px; font-weight: 600; }}"
            )
            self.tags_layout.addWidget(lbl)

    def _render_fields(self, fields: list):
        """清空并重建所有字段行。"""
        # 移除旧字段行（保留末尾 stretch）
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sorted_fields = sorted(fields, key=lambda f: f.get("order", 0))

        for field in sorted_fields:
            ftype = field.get("type", "text")
            label = field.get("label", "")
            value = field.get("value", "")

            if not value:
                continue   # 空值字段不显示

            if ftype == "date_domain":
                # date_domain 拆分为两行
                if "|" in value:
                    domain, expire = value.split("|", 1)
                    domain = domain.strip()
                    expire = expire.strip()
                else:
                    domain = value
                    expire = ""

                row = _FieldRow(
                    label=label,
                    value=domain,
                    field_type="text",
                    field_id=field.get("id", ""),
                    entry_id=self._current_entry_id,
                )
                self.fields_layout.insertWidget(
                    self.fields_layout.count() - 1, row)
                self._field_rows.append(row)

                if expire:
                    expire_row = _FieldRow(
                        label=f"{label} 到期",
                        value=expire,
                        field_type="date",
                        field_id=field.get("id", "") + "_expire",
                        entry_id=self._current_entry_id,
                    )
                    self.fields_layout.insertWidget(
                        self.fields_layout.count() - 1, expire_row)
                    self._field_rows.append(expire_row)

            else:
                row = _FieldRow(
                    label=label,
                    value=value,
                    field_type=ftype,
                    field_id=field.get("id", ""),
                    entry_id=self._current_entry_id,
                )
                self.fields_layout.insertWidget(
                    self.fields_layout.count() - 1, row)
                self._field_rows.append(row)

    # ─────────────────────────────────────────
    # 显示/隐藏状态切换
    # ─────────────────────────────────────────

    def _show_empty(self):
        self._current_entry_id = None
        self.empty_widget.setVisible(True)
        self.content_widget.setVisible(False)

    def _show_content(self):
        self.empty_widget.setVisible(False)
        self.content_widget.setVisible(True)

    def clear(self):
        """外部调用：清空面板并销毁字段行控件，回到空状态。

        字段行 QLabel 中可能持有已显示的明文，必须销毁而不能只隐藏。
        """
        # 销毁所有字段行（保留末尾 stretch）
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._field_rows = []
        self._show_empty()

    # ─────────────────────────────────────────
    # 按钮动作
    # ─────────────────────────────────────────

    def _do_edit(self):
        """点击编辑按钮：发射信号，由 main_window 切换到编辑模式。"""
        if self._current_entry_id:
            self.edit_requested.emit(self._current_entry_id)

    def _open_url(self):
        """点击 URL：用系统浏览器打开（仅放行 http/https 协议）。"""
        url = self.url_lbl.text().strip()
        if not url:
            return

        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
            # file:、ftp:、javascript:、mailto: 等协议会交给系统处理器
            # 执行，条目数据可能来自导入或同步，不能无条件信任。
            # 注意必须按 scheme 解析而不是查 "://"：javascript:alert(1)
            # 这类无 "//" 的协议同样要拦截
            QMessageBox.warning(
                self, "已阻止打开网址",
                f"网址「{url}」不是 http/https 链接，已阻止打开。\n"
                "如需访问，请手动复制到浏览器地址栏。")
            return
        if not parsed.scheme:
            url = "https://" + url   # 未写协议的域名按 https 处理

        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def _copy_to_clipboard(self, text: str):
        """复制文本到剪贴板，并安排到期自动清空（与 secret 字段复制一致）。"""
        if not text:
            return
        QApplication.clipboard().setText(text)
        note_clipboard_copy(text)
        QTimer.singleShot(
            CLIPBOARD_CLEAR_SECONDS * 1000,
            lambda: _clear_clipboard_if_matches(text),
        )

    # ─────────────────────────────────────────
    # 外部刷新接口
    # ─────────────────────────────────────────

    def refresh_current(self):
        """
        外部调用：重新加载当前条目（保存后刷新）。
        """
        if self._current_entry_id:
            self.load_entry(self._current_entry_id)

    @property
    def current_entry_id(self) -> str | None:
        return self._current_entry_id


# ─────────────────────────────────────────────
# 单个字段行
# ─────────────────────────────────────────────

class _FieldRow(QWidget):
    """
    详情面板中的单行字段显示。

    - text / date：直接显示值 + [复制] 按钮
    - secret：默认显示 ••••••••，提供 [显示] 和 [复制] 按钮
    """

    def __init__(self, label: str, value: str,
                 field_type: str, field_id: str,
                 entry_id: str | None = None, parent=None):
        super().__init__(parent)
        self._label     = label
        self._raw_value = value        # 原始值（secret 为 ENC: 字符串）
        self._field_type = field_type
        self._field_id  = field_id
        self._entry_id  = entry_id     # version 2 解密 AAD 需要条目 ID
        self._revealed  = False        # secret 字段当前是否已显示明文

        self._build_ui()

    def _build_ui(self):
        # 行内容（名称列 + 值列 + 按钮列）装进 row_widget，
        # row_widget 与底部分隔线再由本 widget 的垂直布局排列
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row_widget = QWidget()
        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(0)

        # ── 字段名称列
        label_lbl = QLabel(self._label)
        label_lbl.setProperty("class", "field-label")
        label_lbl.setFixedWidth(110)
        label_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        label_lbl.setWordWrap(False)
        layout.addWidget(label_lbl)

        # ── 值列
        value_col = QVBoxLayout()
        value_col.setSpacing(2)
        value_col.setContentsMargins(0, 0, 0, 0)

        if self._field_type == "secret":
            # 打码显示
            self.value_lbl = QLabel("••••••••")
            self.value_lbl.setProperty("class", "masked")
        else:
            display_text = self._format_display_value()
            self.value_lbl = QLabel(display_text)
            self.value_lbl.setProperty("class", "field-value")
            self.value_lbl.setWordWrap(True)
            self.value_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)

        value_col.addWidget(self.value_lbl)
        layout.addLayout(value_col, stretch=1)

        # ── 按钮列
        btn_col = QVBoxLayout()
        btn_col.setSpacing(3)
        btn_col.setContentsMargins(8, 0, 0, 0)
        btn_col.setAlignment(Qt.AlignTop)

        if self._field_type == "secret":
            self.reveal_btn = QPushButton()
            self.reveal_btn.setProperty("class", "icon-btn")
            self.reveal_btn.setFixedSize(28, 26)
            self.reveal_btn.setIcon(_icon("eye", color="#b3b3b3", size=14))
            self.reveal_btn.setIconSize(QSize(14, 14))
            self.reveal_btn.setToolTip("显示")
            self.reveal_btn.clicked.connect(self._toggle_reveal)
            btn_col.addWidget(self.reveal_btn)

        copy_btn = QPushButton()
        copy_btn.setProperty("class", "icon-btn")
        copy_btn.setFixedSize(28, 26)
        copy_btn.setIcon(_icon("copy", color="#b3b3b3", size=14))
        copy_btn.setIconSize(QSize(14, 14))
        copy_btn.setToolTip("复制")
        copy_btn.clicked.connect(self._do_copy)
        btn_col.addWidget(copy_btn)

        self._copy_btn = copy_btn
        layout.addLayout(btn_col)

        outer.addWidget(row_widget)

        # 底部分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        outer.addWidget(sep)

    def _format_display_value(self) -> str:
        """格式化 text/date 类型的显示值。"""
        if self._field_type == "date":
            # 尝试格式化为更友好的日期
            from datetime import datetime, date
            try:
                d = datetime.strptime(self._raw_value, "%Y-%m-%d").date()
                today = date.today()
                diff = (d - today).days
                if diff < 0:
                    return f"{self._raw_value}（已过期 {abs(diff)} 天）"
                elif diff <= 30:
                    return f"{self._raw_value}（还有 {diff} 天）"
                else:
                    return self._raw_value
            except ValueError:
                return self._raw_value
        return self._raw_value

    # ── Secret 字段显示/隐藏

    def _toggle_reveal(self):
        """切换 secret 字段的明文/打码状态。"""
        if self._revealed:
            # 重新打码
            self.value_lbl.setText("••••••••")
            self.value_lbl.setProperty("class", "masked")
            self.reveal_btn.setIcon(_icon("eye", color="#b3b3b3", size=14))
            self.reveal_btn.setToolTip("显示")
            self._revealed = False
        else:
            # 解密并显示
            plaintext = self._decrypt()
            if plaintext is None:
                return
            self.value_lbl.setText(plaintext)
            self.value_lbl.setProperty("class", "field-value")
            self.value_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.reveal_btn.setIcon(_icon("eye-off", color="#f5a623", size=14))
            self.reveal_btn.setToolTip("隐藏")
            self._revealed = True

        # 强制刷新样式
        self.value_lbl.style().unpolish(self.value_lbl)
        self.value_lbl.style().polish(self.value_lbl)

    # ── 复制

    def _do_copy(self):
        """复制字段值到剪贴板。"""
        if self._field_type == "secret":
            plaintext = self._decrypt()
            if plaintext is None:
                return
            text_to_copy = plaintext
        elif self._field_type == "date_domain":
            # date_domain 已被拆分，此处不会出现
            text_to_copy = self._raw_value
        else:
            text_to_copy = self._raw_value

        QApplication.clipboard().setText(text_to_copy)
        note_clipboard_copy(text_to_copy)

        # 复制成功：短暂改变图标提示
        self._copy_btn.setIcon(_icon("check", color="#1ed760", size=14))
        self._copy_btn.setToolTip("已复制！")
        if getattr(self, "_copy_timer", None) is None:
            self._copy_timer = QTimer(self)
            self._copy_timer.setSingleShot(True)
            self._copy_timer.timeout.connect(self._restore_copy_icon)
        self._copy_timer.start(1200)

        # 安全加固：到期自动清空剪贴板。
        # 用应用级 singleShot 而非挂在本控件上的 QTimer——切换条目或
        # 锁屏会销毁字段行，控件级定时器会随之失效，密码将永久留在
        # 剪贴板；应用级定时器不受控件销毁影响。
        # 仅当剪贴板内容仍是刚复制的值时才清空，避免覆盖用户后续复制的内容
        QTimer.singleShot(
            CLIPBOARD_CLEAR_SECONDS * 1000,
            lambda: _clear_clipboard_if_matches(text_to_copy),
        )

    def _restore_copy_icon(self):
        self._copy_btn.setIcon(_icon("copy", color="#b3b3b3", size=14))
        self._copy_btn.setToolTip("复制")

    # ── 解密

    def _decrypt(self) -> str | None:
        """
        解密 secret 字段，返回明文；失败时弹窗提示并返回 None。
        """
        if session.session_key is None:
            QMessageBox.warning(
                self, "未登录", "会话已过期，请重新登录。")
            return None
        try:
            return decrypt_field(
                self._raw_value, session.session_key,
                aad=field_aad(session.vault_data, self._entry_id,
                              self._field_id))
        except (DecryptError, ValueError) as e:
            # ValueError：密文格式损坏，或 version 2 文件缺 ID 无法构造 AAD
            QMessageBox.warning(
                self, "解密失败",
                f"无法解密字段「{self._label}」：\n{e}\n\n"
                "数据可能已损坏，请检查 vault 文件。"
            )
            return None
        except Exception as e:
            QMessageBox.warning(self, "解密失败", f"未知错误：{e}")
            return None
