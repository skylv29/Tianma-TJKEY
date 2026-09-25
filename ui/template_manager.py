# ui/template_manager.py
# TJKEY 模板管理对话框
#
# 功能：
#   - 查看所有内置模板和自定义模板
#   - 编辑模板字段（内置模板只改字段，不能改名和删除）
#   - 新建自定义模板
#   - 删除自定义模板

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QLineEdit, QComboBox, QFrame, QMessageBox,
    QScrollArea, QWidget,
)
from PySide6.QtCore import Qt, Signal, QSize
from icons import icon as _icon, pixmap as _pixmap
from PySide6.QtGui import QColor

from session import session
from ui.vault_sync import save_vault_or_lock
from vault_io import (
    add_custom_template, update_template,
    delete_custom_template,
)
from crypto import generate_id

FIELD_TYPES = [
    ("text",        "普通文本"),
    ("secret",      "加密字段"),
    ("date",        "日期"),
    ("date_domain", "域名 + 到期日"),
]
FIELD_TYPE_LABELS = {t: l for t, l in FIELD_TYPES}


class TemplateManagerDialog(QDialog):
    """模板管理主对话框：左侧列表，右侧编辑区。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模板管理")
        # 最小高度须容纳左列（列表头 36 + 列表 + 新建按钮 36），
        # 否则底部"新建模板"按钮会被裁剪；默认再放大一些更从容
        self.setMinimumSize(660, 520)
        self.resize(720, 560)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._current_tpl_id: str | None = None
        self._build_ui()
        self._refresh_list()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 左侧：模板列表
        left = QFrame()
        left.setFixedWidth(200)
        left.setProperty("class", "nav-panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        list_header = QLabel("  模板列表")
        list_header.setProperty("class", "section-header")
        list_header.setFixedHeight(36)
        left_layout.addWidget(list_header)

        self.tpl_list = QListWidget()
        self.tpl_list.currentItemChanged.connect(self._on_tpl_selected)
        left_layout.addWidget(self.tpl_list)

        new_btn = QPushButton("  新建模板")
        new_btn.setProperty("class", "ghost")
        new_btn.setFixedHeight(36)
        # 内联覆盖全局 QSS 的 min-height/padding/margin：
        # 全局 QPushButton { min-height:30px; padding:7px 18px } 会让按钮
        # 实际高度膨胀到 46px (30+7+7+1+1)，超出 setFixedHeight(36)，
        # 导致底边溢出对话框。QSS min-height 凌驾于 setFixedHeight 之上，
        # 必须在内联样式中直接指定目标尺寸：
        #   34px内容 + 0px padding + 1px*2 border = 36px 总高
        # 同时保留 ghost 外观（transparent bg / border / border-radius
        # 由 class 选择器提供，不被内联覆盖）。
        new_btn.setStyleSheet(
            "QPushButton { min-height: 34px; max-height: 34px; "
            "padding: 0px 18px; margin: 0px; }"
        )
        new_btn.setIcon(_icon("plus", color="#b3b3b3", size=14))
        new_btn.setIconSize(QSize(14, 14))
        new_btn.clicked.connect(self._do_new_template)
        left_layout.addWidget(new_btn)

        root.addWidget(left)

        # 分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        sep.setFixedWidth(1)
        root.addWidget(sep)

        # ── 右侧：编辑区
        self.right_stack_widget = QFrame()
        self.right_stack_widget.setProperty("class", "list-panel")
        right_layout = QVBoxLayout(self.right_stack_widget)
        right_layout.setContentsMargins(20, 16, 20, 16)
        right_layout.setSpacing(12)

        # 空状态
        self.empty_lbl = QLabel("← 从左侧选择一个模板")
        self.empty_lbl.setProperty("class", "hint")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.empty_lbl)

        # 编辑区（动态创建）
        self.edit_frame = QWidget()
        self.edit_frame.setVisible(False)
        self.edit_frame_layout = QVBoxLayout(self.edit_frame)
        self.edit_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_frame_layout.setSpacing(10)
        right_layout.addWidget(self.edit_frame, stretch=1)

        root.addWidget(self.right_stack_widget, stretch=1)

    # ─────────────────────────────────────────
    # 模板列表刷新
    # ─────────────────────────────────────────

    def _refresh_list(self, select_id: str = None):
        self.tpl_list.blockSignals(True)
        self.tpl_list.clear()

        templates = session.vault_data.get("templates", []) if session.vault_data else []
        builtin = [t for t in templates if t.get("is_builtin")]
        custom  = [t for t in templates if not t.get("is_builtin")]

        if builtin:
            sep = QListWidgetItem("── 内置模板 ──")
            sep.setFlags(Qt.NoItemFlags)
            sep.setForeground(QColor("#6c7086"))
            self.tpl_list.addItem(sep)
            for tpl in builtin:
                item = QListWidgetItem(f"  {tpl['name']}")
                item.setData(Qt.UserRole, tpl["id"])
                self.tpl_list.addItem(item)
                if tpl["id"] == select_id:
                    self.tpl_list.setCurrentItem(item)

        if custom:
            sep2 = QListWidgetItem("── 自定义模板 ──")
            sep2.setFlags(Qt.NoItemFlags)
            sep2.setForeground(QColor("#6c7086"))
            self.tpl_list.addItem(sep2)
            for tpl in custom:
                item = QListWidgetItem(f"  ⭐  {tpl['name']}")
                item.setData(Qt.UserRole, tpl["id"])
                self.tpl_list.addItem(item)
                if tpl["id"] == select_id:
                    self.tpl_list.setCurrentItem(item)

        self.tpl_list.blockSignals(False)

    # ─────────────────────────────────────────
    # 模板选中
    # ─────────────────────────────────────────

    def _on_tpl_selected(self, current: QListWidgetItem, _):
        if current is None or not current.data(Qt.UserRole):
            return
        tpl_id = current.data(Qt.UserRole)
        self._load_template_editor(tpl_id)

    def _load_template_editor(self, tpl_id: str):
        """在右侧显示模板编辑界面。"""
        templates = session.vault_data.get("templates", [])
        tpl = next((t for t in templates if t["id"] == tpl_id), None)
        if not tpl:
            return

        self._current_tpl_id = tpl_id
        is_builtin = tpl.get("is_builtin", False)

        # 清空编辑区：先隐藏再延迟销毁——deleteLater 要等事件循环处理，
        # 若只销毁不隐藏，切换模板瞬间旧控件会与新控件重叠闪现
        while self.edit_frame_layout.count():
            item = self.edit_frame_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        self.empty_lbl.setVisible(False)
        self.edit_frame.setVisible(True)

        # 模板名称
        name_row = QHBoxLayout()
        name_lbl = QLabel("模板名称")
        name_lbl.setProperty("class", "field-label")
        name_lbl.setFixedWidth(70)
        name_row.addWidget(name_lbl)

        self.tpl_name_input = QLineEdit(tpl["name"])
        self.tpl_name_input.setReadOnly(is_builtin)
        if is_builtin:
            self.tpl_name_input.setToolTip("内置模板名称不可修改")
        name_row.addWidget(self.tpl_name_input)

        name_widget = QWidget()
        name_widget.setLayout(name_row)
        self.edit_frame_layout.addWidget(name_widget)

        # 字段列表标题
        fields_header = QLabel("字段列表")
        fields_header.setProperty("class", "section-header")
        self.edit_frame_layout.addWidget(fields_header)

        # 可滚动字段列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        fields_container = QWidget()
        self._fields_layout = QVBoxLayout(fields_container)
        self._fields_layout.setContentsMargins(0, 0, 0, 0)
        self._fields_layout.setSpacing(4)

        self._tpl_field_rows: list[_TplFieldRow] = []
        for i, field in enumerate(tpl.get("fields", [])):
            row = _TplFieldRow(
                label=field.get("label", ""),
                ftype=field.get("type", "text"),
                idx=i,
                can_delete=(len(tpl.get("fields", [])) > 1),
            )
            row.delete_requested.connect(self._remove_tpl_field)
            row.move_up_requested.connect(self._move_tpl_field_up)
            row.move_down_requested.connect(self._move_tpl_field_down)
            self._fields_layout.addWidget(row)
            self._tpl_field_rows.append(row)

        self._fields_layout.addStretch()
        scroll.setWidget(fields_container)
        self.edit_frame_layout.addWidget(scroll, stretch=1)

        # 添加字段按钮
        add_btn = QPushButton("  添加字段")
        add_btn.setProperty("class", "ghost")
        add_btn.setIcon(_icon("plus", color="#b3b3b3", size=14))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.clicked.connect(self._add_tpl_field)
        self.edit_frame_layout.addWidget(add_btn)

        # 操作按钮行
        btn_row = QHBoxLayout()

        if not is_builtin:
            del_btn = QPushButton("  删除模板")
            del_btn.setProperty("class", "danger")
            del_btn.setIcon(_icon("trash", color="#f3727f", size=14))
            del_btn.setIconSize(QSize(14, 14))
            del_btn.clicked.connect(self._do_delete_template)
            btn_row.addWidget(del_btn)

        btn_row.addStretch()

        save_btn = QPushButton("  保存")
        save_btn.setProperty("class", "primary")
        save_btn.setIcon(_icon("check", color="#121212", size=14))
        save_btn.setIconSize(QSize(14, 14))
        save_btn.clicked.connect(self._do_save_template)
        btn_row.addWidget(save_btn)

        btn_widget = QWidget()
        btn_widget.setLayout(btn_row)
        self.edit_frame_layout.addWidget(btn_widget)

    # ─────────────────────────────────────────
    # 字段操作
    # ─────────────────────────────────────────

    def _add_tpl_field(self):
        idx = len(self._tpl_field_rows)
        row = _TplFieldRow(label="", ftype="text", idx=idx, can_delete=True)
        row.delete_requested.connect(self._remove_tpl_field)
        row.move_up_requested.connect(self._move_tpl_field_up)
        row.move_down_requested.connect(self._move_tpl_field_down)
        # 插入到 stretch 之前
        count = self._fields_layout.count()
        self._fields_layout.insertWidget(count - 1, row)
        self._tpl_field_rows.append(row)

    def _remove_tpl_field(self, idx: int):
        if len(self._tpl_field_rows) <= 1:
            QMessageBox.warning(self, "提示", "模板至少需要保留一个字段。")
            return
        if 0 <= idx < len(self._tpl_field_rows):
            row = self._tpl_field_rows.pop(idx)
            row.setParent(None)
            row.deleteLater()
            self._reindex_rows()

    def _move_tpl_field_up(self, idx: int):
        if idx <= 0:
            return
        self._swap_tpl_rows(idx, idx - 1)

    def _move_tpl_field_down(self, idx: int):
        if idx >= len(self._tpl_field_rows) - 1:
            return
        self._swap_tpl_rows(idx, idx + 1)

    def _swap_tpl_rows(self, i: int, j: int):
        rows = self._tpl_field_rows
        rows[i], rows[j] = rows[j], rows[i]
        for row in rows:
            self._fields_layout.removeWidget(row)
        for row in rows:
            self._fields_layout.insertWidget(
                self._fields_layout.count() - 1, row)
        self._reindex_rows()

    def _reindex_rows(self):
        for i, row in enumerate(self._tpl_field_rows):
            row.set_index(i)

    # ─────────────────────────────────────────
    # 新建 / 保存 / 删除模板
    # ─────────────────────────────────────────

    def _do_new_template(self):
        name, ok = self._ask_name("新建自定义模板", "请输入模板名称：")
        if not ok or not name:
            return

        default_fields = [
            {"label": "用户名", "type": "text"},
            {"label": "密码",   "type": "secret"},
            {"label": "备注",   "type": "text"},
        ]
        new_tpl = None

        def _create():
            nonlocal new_tpl
            new_tpl = add_custom_template(session.vault_data, name,
                                          default_fields)

        if not self._mutate_and_save(_create):
            return
        self._refresh_list(select_id=new_tpl["id"])
        self._load_template_editor(new_tpl["id"])

    def _do_save_template(self):
        if not self._current_tpl_id:
            return

        # 收集字段
        new_fields = []
        for row in self._tpl_field_rows:
            label = row.get_label()
            ftype = row.get_type()
            if label:
                new_fields.append({"label": label, "type": ftype})

        if not new_fields:
            QMessageBox.warning(self, "保存失败", "模板至少需要一个字段。")
            return

        # 收集名称（自定义模板可改名）
        new_name = self.tpl_name_input.text().strip() or None

        if not self._mutate_and_save(
                lambda: update_template(session.vault_data, self._current_tpl_id,
                                        name=new_name, fields=new_fields)):
            return
        self._refresh_list(select_id=self._current_tpl_id)
        QMessageBox.information(self, "保存成功", "模板已保存。")

    def _do_delete_template(self):
        if not self._current_tpl_id:
            return

        tpl = next(
            (t for t in session.vault_data.get("templates", [])
             if t["id"] == self._current_tpl_id), None
        )
        if not tpl or tpl.get("is_builtin"):
            return

        reply = QMessageBox.question(
            self, "删除模板",
            f"确认删除模板「{tpl['name']}」？\n已使用该模板创建的条目不受影响。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if not self._mutate_and_save(
                lambda: delete_custom_template(session.vault_data,
                                               self._current_tpl_id)):
            return
        self._current_tpl_id = None
        self.empty_lbl.setVisible(True)
        self.edit_frame.setVisible(False)
        self._refresh_list()

    # ─────────────────────────────────────────
    # 工具
    # ─────────────────────────────────────────

    def _mutate_and_save(self, mutate_fn) -> bool:
        """执行 mutate_fn 后保存；写盘失败时回滚内存，避免界面/磁盘分叉。"""
        import copy as _copy
        snapshot = _copy.deepcopy(session.vault_data)
        mutate_fn()
        if not save_vault_or_lock():
            if not session.is_locked() and snapshot is not None:
                session.vault_data.clear()
                session.vault_data.update(snapshot)
            return False
        return True

    def _ask_name(self, title: str, prompt: str) -> tuple:
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getText(self, title, prompt)


# ─────────────────────────────────────────────
# 模板字段行
# ─────────────────────────────────────────────

class _TplFieldRow(QWidget):
    """模板编辑区中的单行字段（label 输入 + type 下拉 + 操作按钮）。"""
    delete_requested   = Signal(int)   # idx
    move_up_requested  = Signal(int)
    move_down_requested = Signal(int)

    def __init__(self, label: str, ftype: str, idx: int,
                 can_delete: bool = True, parent=None):
        super().__init__(parent)
        self._idx = idx
        self._build_ui(label, ftype, can_delete)

    def _build_ui(self, label: str, ftype: str, can_delete: bool):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # 全局 QSS 的 padding+min-height（QLineEdit/QComboBox/QPushButton）
        # 会把控件撑到比 setFixedHeight 更高，28px 定高下文字被上下裁剪。
        # 整行统一内联重置为 36px 定高（34 内容 + 2 边框）。
        # 注意必须带显式类选择器：无选择器的声明串会级联到子控件——
        # QComboBox 的弹出选项列表正是其子控件，会被 max-height 压成
        # 一行高（只剩"普通文本"一个选项可见）
        input_qss = "QLineEdit { min-height: 34px; max-height: 34px; padding: 0px 12px; }"
        combo_qss = "QComboBox { min-height: 34px; max-height: 34px; padding: 0px 12px; }"
        btn_qss = ("QPushButton { min-height: 0px; max-height: 36px; "
                   "min-width: 0px; padding: 0px; margin: 0px; }")

        self.label_input = QLineEdit(label)
        self.label_input.setPlaceholderText("字段名称")
        self.label_input.setStyleSheet(input_qss)
        layout.addWidget(self.label_input, stretch=2)

        self.type_combo = QComboBox()
        for ft, fl in FIELD_TYPES:
            self.type_combo.addItem(fl, ft)
            if ft == ftype:
                self.type_combo.setCurrentIndex(self.type_combo.count() - 1)
        self.type_combo.setStyleSheet(combo_qss)
        layout.addWidget(self.type_combo, stretch=1)

        for icon_name, attr in [("chevron-up",   "move_up_requested"),
                                  ("chevron-down", "move_down_requested")]:
            btn = QPushButton()
            btn.setProperty("class", "icon-btn")
            btn.setStyleSheet(btn_qss)
            btn.setFixedSize(28, 36)
            btn.setIcon(_icon(icon_name, color="#6a6a6a", size=13))
            btn.setIconSize(QSize(13, 13))
            sig = getattr(self, attr)
            btn.clicked.connect(lambda _, s=sig: s.emit(self._idx))
            layout.addWidget(btn)

        del_btn = QPushButton()
        del_btn.setProperty("class", "icon-btn")
        del_btn.setStyleSheet(btn_qss)
        del_btn.setFixedSize(28, 36)
        del_btn.setIcon(_icon("x", color="#6a6a6a", size=13))
        del_btn.setIconSize(QSize(13, 13))
        del_btn.setEnabled(can_delete)
        del_btn.setToolTip("删除此字段")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self._idx))
        layout.addWidget(del_btn)

    def set_index(self, idx: int):
        self._idx = idx

    def get_label(self) -> str:
        return self.label_input.text().strip()

    def get_type(self) -> str:
        return self.type_combo.currentData()
