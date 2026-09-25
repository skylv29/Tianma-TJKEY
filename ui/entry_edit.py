# ui/entry_edit.py
# TJKEY 条目编辑面板
#
# 功能：
#   - 新建条目（从模板预填字段结构）
#   - 编辑已有条目（secret 字段进入编辑模式时自动解密）
#   - 字段增删改、顺序调整
#   - 保存时对 secret 字段重新加密
#   - 取消时丢弃所有修改

import os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QComboBox, QScrollArea,
    QMessageBox, QDialog, QSpinBox, QCheckBox, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from icons import icon as _icon

from session import session
from ui.vault_sync import save_vault_or_lock
from vault_io import (
    get_entry_by_id, add_entry, update_entry, delete_entry,
    build_entry_from_template,
    get_category_by_id, get_subcategory_by_id,
)
from crypto import (
    encrypt_field, decrypt_field, is_encrypted, field_aad,
    generate_id, generate_field_id, generate_password, now_iso,
)


def _is_valid_date(s: str) -> bool:
    """校验 YYYY-MM-DD 格式的合法日期（到期扫描只认这种格式）。"""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# ─────────────────────────────────────────────
# 字段类型配置
# ─────────────────────────────────────────────

FIELD_TYPES = [
    ("text",        "普通文本"),
    ("secret",      "加密字段（密码/Key）"),
    ("date",        "日期"),
    ("date_domain", "域名 + 到期日"),
]

FIELD_TYPE_LABELS = {t: l for t, l in FIELD_TYPES}


# ─────────────────────────────────────────────
# 编辑面板主体
# ─────────────────────────────────────────────

class EntryEditPanel(QFrame):
    """
    条目编辑面板（新建 + 修改 共用）。

    发射信号：
        save_done(entry_id)    保存成功，通知主窗口切回查看模式
        cancel_requested()     用户点取消，通知主窗口切回查看模式
        entry_deleted(entry_id) 条目被删除
    """
    save_done        = Signal(str)   # entry_id
    cancel_requested = Signal()
    entry_deleted    = Signal(str)   # entry_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "detail-panel")
        self.setMinimumWidth(300)

        self._entry_id: str | None = None   # None = 新建模式
        self._is_new   = True
        self._field_rows: list["_EditFieldRow"] = []
        # 进入编辑时解密失败的 secret 字段 ID：
        # 保存时若用户未重新输入，保留原密文而不是写入空值覆盖
        self._decrypt_failed_ids: set[str] = set()

        self._build_ui()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部操作栏
        action_bar = QFrame()
        action_bar.setFixedHeight(52)
        ab_layout = QHBoxLayout(action_bar)
        ab_layout.setContentsMargins(20, 8, 16, 8)
        ab_layout.setSpacing(8)

        self.mode_lbl = QLabel("新建条目")
        self.mode_lbl.setProperty("class", "entry-name")
        ab_layout.addWidget(self.mode_lbl)

        ab_layout.addStretch()

        self.save_btn = QPushButton("  保存")
        self.save_btn.setIcon(_icon("check", color="#121212", size=14))
        self.save_btn.setIconSize(QSize(14, 14))
        self.save_btn.setProperty("class", "primary")
        self.save_btn.setFixedHeight(32)
        self.save_btn.clicked.connect(self._do_save)
        ab_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setProperty("class", "ghost")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.clicked.connect(self._do_cancel)
        ab_layout.addWidget(self.cancel_btn)

        root.addWidget(action_bar)

        # 分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        root.addWidget(sep)

        # ── 可滚动编辑区
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self.edit_container = QWidget()
        self.edit_layout = QVBoxLayout(self.edit_container)
        self.edit_layout.setContentsMargins(20, 16, 16, 16)
        self.edit_layout.setSpacing(12)

        # 基础信息区
        self._build_base_section()

        # 字段区标题
        fields_header = QLabel("自定义字段")
        fields_header.setProperty("class", "section-header")
        self.edit_layout.addWidget(fields_header)

        # 字段容器（动态增删）
        self.fields_container = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(4)
        self.edit_layout.addWidget(self.fields_container)

        # 添加字段按钮
        add_field_btn = QPushButton("  添加字段")
        add_field_btn.setProperty("class", "ghost")
        add_field_btn.setIcon(_icon("plus", color="#b3b3b3", size=14))
        add_field_btn.setIconSize(QSize(14, 14))
        add_field_btn.clicked.connect(self._do_add_field)
        self.edit_layout.addWidget(add_field_btn)

        self.edit_layout.addStretch()

        # 删除条目按钮（编辑模式才显示）
        self.delete_btn = QPushButton("  移入回收站")
        self.delete_btn.setProperty("class", "danger")
        self.delete_btn.setFixedHeight(32)
        self.delete_btn.setIcon(_icon("trash", color="#f3727f", size=14))
        self.delete_btn.setIconSize(QSize(14, 14))
        self.delete_btn.setToolTip("移入回收站，可稍后恢复")
        self.delete_btn.clicked.connect(self._do_delete)
        self.delete_btn.setVisible(False)
        self.edit_layout.addWidget(self.delete_btn)

        self._scroll_area.setWidget(self.edit_container)
        root.addWidget(self._scroll_area, stretch=1)

    def _build_base_section(self):
        """构建基础字段区（名称、分类、URL、标签）。"""
        # 名称
        self.edit_layout.addWidget(self._make_field_label("条目名称 *"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("必填，如：Cloudflare 主号")
        self.edit_layout.addWidget(self.name_input)

        # 分类（大类 + 小类）
        self.edit_layout.addWidget(self._make_field_label("分类"))
        cat_row = QHBoxLayout()
        cat_row.setSpacing(8)

        self.cat_combo = QComboBox()
        self.cat_combo.addItem("── 未分类 ──", None)
        self.cat_combo.currentIndexChanged.connect(self._on_cat_changed)
        cat_row.addWidget(self.cat_combo, stretch=1)

        self.sub_combo = QComboBox()
        self.sub_combo.addItem("── 无子类 ──", None)
        self.sub_combo.setEnabled(False)
        cat_row.addWidget(self.sub_combo, stretch=1)

        cat_widget = QWidget()
        cat_widget.setLayout(cat_row)
        self.edit_layout.addWidget(cat_widget)

        # URL
        self.edit_layout.addWidget(self._make_field_label("登录网址（选填）"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://...")
        self.edit_layout.addWidget(self.url_input)

        # 标签
        self.edit_layout.addWidget(self._make_field_label("标签（逗号分隔，选填）"))
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("如：cloudflare, 主力, 域名")
        self.edit_layout.addWidget(self.tags_input)

    def _make_field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "field-label")
        return lbl

    # ─────────────────────────────────────────
    # 加载数据（新建 / 编辑）
    # ─────────────────────────────────────────

    def load_new_entry(self, tpl_id: str, cat_id=None, sub_id=None):
        """
        进入新建模式：从模板构建空白条目结构并填入编辑界面。
        """
        self._is_new = True
        self._entry_id = None
        self.mode_lbl.setText("新建条目")
        self.delete_btn.setVisible(False)

        # 构建空白条目
        entry = build_entry_from_template(tpl_id, session.vault_data)
        entry["category_id"]    = cat_id
        entry["subcategory_id"] = sub_id

        self._populate_ui(entry, decrypt_secrets=False)

    def load_edit_entry(self, entry_id: str):
        """
        进入编辑模式：加载已有条目，secret 字段自动解密填入输入框。
        """
        if not session.vault_data:
            return
        entry = get_entry_by_id(session.vault_data, entry_id)
        if entry is None:
            return

        self._is_new = False
        self._entry_id = entry_id
        self.mode_lbl.setText(f"编辑：{entry.get('name', '')}")
        self.delete_btn.setVisible(True)

        self._populate_ui(entry, decrypt_secrets=True)

    def _populate_ui(self, entry: dict, decrypt_secrets: bool):
        """将条目数据填入所有输入控件。"""
        decrypt_fail_count = 0

        self.name_input.setText(entry.get("name", ""))
        self.url_input.setText(entry.get("url", ""))
        self.tags_input.setText(", ".join(entry.get("tags", [])))

        # 填充分类下拉框
        self._populate_cat_combos(
            entry.get("category_id"),
            entry.get("subcategory_id"),
        )

        # 清空旧字段行
        self._clear_field_rows()
        self._decrypt_failed_ids = set()

        # 填充字段列表
        sorted_fields = sorted(
            entry.get("fields", []),
            key=lambda f: f.get("order", 0)
        )
        for field in sorted_fields:
            label  = field.get("label", "")
            ftype  = field.get("type", "text")
            value  = field.get("value", "")
            fid    = field.get("id", "")
            if not fid:
                # 缺 id 的字段基于当前已创建行生成唯一 id
                # （不能用空列表调 generate_field_id，否则多个缺 id 字段
                #  都会得到 fld_001）
                existing = [r.field_id for r in self._field_rows]
                fid = generate_field_id(existing)

            # secret 字段：进入编辑模式时解密；失败则清空该字段并记录 id，
            # 避免密文留在输入框中被二次加密，同时防止保存时空值覆盖原数据
            if ftype == "secret" and value and decrypt_secrets:
                try:
                    # AAD 用原始 field id（而非回填的 fid）：
                    # v2 文件缺 ID 属于格式错误，应走失败分支而非错位解密
                    value = decrypt_field(
                        value, session.session_key,
                        aad=field_aad(session.vault_data, entry.get("id"),
                                      field.get("id")))
                except Exception:
                    value = ""
                    decrypt_fail_count += 1
                    self._decrypt_failed_ids.add(fid)

            self._add_field_row(label=label, ftype=ftype,
                                value=value, fid=fid)

        if decrypt_fail_count > 0:
            QMessageBox.warning(
                self, "解密警告",
                f"有 {decrypt_fail_count} 个加密字段解密失败，已清空等待重新输入。\n"
                "若不重新输入直接保存，将保留这些字段的原有加密数据（不会被清空）。"
            )

        QTimer.singleShot(0, self._safe_scroll_to_top)

    def _safe_scroll_to_top(self):
        # 延迟回调触发时面板可能已被销毁（快速切条目/锁屏），
        # 先校验 C++ 对象存活，避免 RuntimeError
        import shiboken6
        if shiboken6.isValid(self):
            self._scroll_to_top()

    def _scroll_to_top(self):
        self._scroll_area.verticalScrollBar().setValue(0)

    def _populate_cat_combos(self, cat_id, sub_id):
        """填充大类/小类下拉框并恢复选中状态。"""
        self.cat_combo.blockSignals(True)
        self.cat_combo.clear()
        self.cat_combo.addItem("── 未分类 ──", None)

        categories = sorted(
            session.vault_data.get("categories", []),
            key=lambda c: c.get("order", 0),
        )
        target_cat_idx = 0
        for i, cat in enumerate(categories, start=1):
            self.cat_combo.addItem(f"  {cat['name']}", cat["id"])
            self.cat_combo.setItemIcon(
                self.cat_combo.count() - 1,
                _icon("folder", color="#b3b3b3", size=14)
            )
            if cat["id"] == cat_id:
                target_cat_idx = i

        self.cat_combo.setCurrentIndex(target_cat_idx)
        self.cat_combo.blockSignals(False)

        # 触发子类填充
        self._on_cat_changed(target_cat_idx)

        # 恢复子类选中
        if sub_id:
            for i in range(self.sub_combo.count()):
                if self.sub_combo.itemData(i) == sub_id:
                    self.sub_combo.setCurrentIndex(i)
                    break

    def _on_cat_changed(self, idx: int):
        """大类下拉框变化时更新子类下拉框。"""
        self.sub_combo.blockSignals(True)
        self.sub_combo.clear()
        self.sub_combo.addItem("── 无子类 ──", None)

        cat_id = self.cat_combo.itemData(idx)
        if cat_id and session.vault_data:
            cat = get_category_by_id(session.vault_data, cat_id)
            if cat:
                subs = sorted(
                    cat.get("subcategories", []),
                    key=lambda s: s.get("order", 0)
                )
                for sub in subs:
                    self.sub_combo.addItem(f"  {sub['name']}", sub["id"])
                    self.sub_combo.setItemIcon(
                        self.sub_combo.count() - 1,
                        _icon("folder", color="#6a6a6a", size=13)
                    )

        self.sub_combo.setEnabled(self.sub_combo.count() > 1)
        self.sub_combo.blockSignals(False)

    # ─────────────────────────────────────────
    # 字段行管理
    # ─────────────────────────────────────────

    def _add_field_row(self, label="", ftype="text", value="", fid=""):
        """添加一行可编辑字段。"""
        if not fid:
            existing = [r.field_id for r in self._field_rows]
            fid = generate_field_id(existing)

        row = _EditFieldRow(
            label=label, ftype=ftype, value=value, field_id=fid
        )
        row.delete_requested.connect(self._remove_field_row)
        row.move_up_requested.connect(self._move_field_up)
        row.move_down_requested.connect(self._move_field_down)

        self.fields_layout.addWidget(row)
        self._field_rows.append(row)

    def _remove_field_row(self, fid: str):
        """删除指定字段行。"""
        for row in self._field_rows:
            if row.field_id == fid:
                self._field_rows.remove(row)
                row.setParent(None)
                row.deleteLater()
                return

    def _move_field_up(self, fid: str):
        """将字段行上移一位。"""
        idx = next((i for i, r in enumerate(self._field_rows)
                    if r.field_id == fid), -1)
        if idx <= 0:
            return
        self._swap_field_rows(idx, idx - 1)

    def _move_field_down(self, fid: str):
        """将字段行下移一位。"""
        idx = next((i for i, r in enumerate(self._field_rows)
                    if r.field_id == fid), -1)
        if idx < 0 or idx >= len(self._field_rows) - 1:
            return
        self._swap_field_rows(idx, idx + 1)

    def _swap_field_rows(self, i: int, j: int):
        """交换两个字段行的位置（同时更新列表和布局）。"""
        rows = self._field_rows
        rows[i], rows[j] = rows[j], rows[i]

        # 重建布局顺序
        for row in rows:
            self.fields_layout.removeWidget(row)
        for row in rows:
            self.fields_layout.addWidget(row)

    def _clear_field_rows(self):
        """清除所有字段行。"""
        for row in self._field_rows:
            row.setParent(None)
            row.deleteLater()
        self._field_rows.clear()

    def _do_add_field(self):
        """弹出字段类型选择对话框，添加新字段。"""
        dlg = _AddFieldDialog(self)
        if dlg.exec() == QDialog.Accepted:
            label, ftype = dlg.get_result()
            if label:
                self._add_field_row(label=label, ftype=ftype)

    def clear(self):
        """清空所有输入（锁屏/重新登录时调用）。

        编辑模式下 secret 字段是解密后的明文，必须销毁输入控件，
        而不能只切换面板可见性。
        """
        self._is_new = True
        self._entry_id = None
        self._decrypt_failed_ids = set()
        self.mode_lbl.setText("新建条目")
        self.delete_btn.setVisible(False)
        self.name_input.clear()
        self.url_input.clear()
        self.tags_input.clear()
        self.cat_combo.blockSignals(True)
        self.cat_combo.setCurrentIndex(0)
        self.cat_combo.blockSignals(False)
        self.sub_combo.clear()
        self.sub_combo.addItem("── 无子类 ──", None)
        self.sub_combo.setEnabled(False)
        self._clear_field_rows()

    # ─────────────────────────────────────────
    # 保存
    # ─────────────────────────────────────────

    def _do_save(self):
        """验证并保存条目。"""
        # 验证名称
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "保存失败", "条目名称不能为空。")
            self.name_input.setFocus()
            return

        if session.session_key is None:
            QMessageBox.warning(self, "保存失败", "会话已过期，请重新登录。")
            return

        # 收集分类
        cat_id = self.cat_combo.currentData()
        sub_id = self.sub_combo.currentData()

        # 收集标签
        tags_raw = self.tags_input.text().strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] \
               if tags_raw else []

        # 先确定条目 ID：version 2 字段加密需用 entry_id 构造 AAD，
        # 新建条目也必须在加密循环之前生成 ID，保证 AAD 与落盘 ID 一致
        now = now_iso()
        if self._is_new:
            entry_id = generate_id("entry_")
        else:
            entry_id = self._entry_id

        # 解密失败字段的原始密文：用户未重新输入时保留原值，防止空值覆盖
        orig_secret_values: dict = {}
        if not self._is_new and self._entry_id and session.vault_data:
            orig_entry = get_entry_by_id(session.vault_data, self._entry_id)
            if orig_entry:
                orig_secret_values = {
                    f.get("id"): f.get("value", "")
                    for f in orig_entry.get("fields", [])
                    if f.get("type") == "secret"
                }

        # 收集并加密字段
        fields = []
        for order, row in enumerate(self._field_rows):
            label  = row.get_label()
            ftype  = row.get_type()
            value  = row.get_value()

            if not label:
                continue   # 跳过无名字段

            if ftype == "secret":
                if (not value
                        and row.field_id in self._decrypt_failed_ids
                        and row.field_id in orig_secret_values):
                    # 解密失败且未重新输入：保留原密文，避免数据永久丢失
                    value = orig_secret_values[row.field_id]
                elif value:
                    if is_encrypted(value):
                        # 输入框里不应出现密文（解密失败已在进入编辑时清空），
                        # 放行会把密文再加密一层，之后需要两次解密才能还原
                        QMessageBox.warning(
                            self, "保存失败",
                            f"字段「{label}」的内容是加密数据（ENC: 开头）而非明文，"
                            "请重新输入该字段的值。"
                        )
                        return
                    try:
                        value = encrypt_field(
                            value, session.session_key,
                            aad=field_aad(session.vault_data, entry_id,
                                          row.field_id))
                    except Exception as e:
                        QMessageBox.warning(
                            self, "加密失败",
                            f"字段「{label}」加密失败：{e}"
                        )
                        return

            if ftype == "date" and value and not _is_valid_date(value):
                # 格式错误的日期会被到期扫描静默跳过，保存前拦下
                QMessageBox.warning(
                    self, "保存失败",
                    f"日期字段「{label}」的值「{value}」不是有效的"
                    "YYYY-MM-DD 日期，请修正后再保存。"
                )
                return

            if ftype == "date_domain":
                domain, _, expire = value.partition("|")
                if expire.strip() and not _is_valid_date(expire.strip()):
                    QMessageBox.warning(
                        self, "保存失败",
                        f"字段「{label}」的到期日期「{expire.strip()}」不是有效的"
                        "YYYY-MM-DD 日期，请修正后再保存。"
                    )
                    return

            fields.append({
                "id":    row.field_id,
                "label": label,
                "type":  ftype,
                "value": value,
                "order": order,
            })

        # 构建条目 dict（entry_id / now 已在字段收集前确定）
        entry_dict = {
            "id":             entry_id,
            "name":           name,
            "category_id":    cat_id,
            "subcategory_id": sub_id,
            "url":            self.url_input.text().strip(),
            "tags":           tags,
            "fields":         fields,
            "updated_at":     now,
        }

        # 写入 vault（带外部修改检测；被拦截时已提示并强制回登录界面）
        import copy as _copy
        pre_snapshot = None if self._is_new else _copy.deepcopy(session.vault_data)

        if self._is_new:
            add_entry(session.vault_data, entry_dict)
        else:
            update_entry(session.vault_data, entry_id, entry_dict)
        if not save_vault_or_lock():
            # 保存失败：若因外部修改被强制锁屏则会话已清空，直接返回；
            # 仅写盘出错时回滚内存修改，避免"界面有、磁盘无"的分叉状态
            if not session.is_locked() and session.vault_data is not None:
                if self._is_new:
                    entries = session.vault_data.get("entries", [])
                    session.vault_data["entries"] = [
                        e for e in entries if e.get("id") != entry_id
                    ]
                elif pre_snapshot is not None:
                    session.vault_data.clear()
                    session.vault_data.update(pre_snapshot)
            return

        # 保存成功后立即清空面板：编辑模式下字段行持有解密后的明文，
        # 尽早销毁，缩小明文暴露窗口
        self.clear()
        self.save_done.emit(entry_id)

    # ─────────────────────────────────────────
    # 取消 / 删除
    # ─────────────────────────────────────────

    def _do_cancel(self):
        self.cancel_requested.emit()

    def _do_delete(self):
        """将当前编辑的条目移入回收站（软删除，可恢复）。"""
        if not self._entry_id:
            return

        entry = get_entry_by_id(session.vault_data, self._entry_id)
        name  = entry["name"] if entry else "该条目"

        reply = QMessageBox.question(
            self, "移入回收站",
            f"确认将「{name}」移入回收站？\n可稍后在左侧「回收站」中恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        eid = self._entry_id
        delete_entry(session.vault_data, eid)
        if not save_vault_or_lock():
            return

        self.clear()
        self.entry_deleted.emit(eid)


# ─────────────────────────────────────────────
# 单行可编辑字段
# ─────────────────────────────────────────────

class _EditFieldRow(QWidget):
    """
    编辑模式中的单行字段组件。

    支持类型：text / secret / date / date_domain
    提供：删除按钮、上移/下移按钮
    """
    delete_requested   = Signal(str)   # field_id
    move_up_requested  = Signal(str)   # field_id
    move_down_requested = Signal(str)  # field_id

    def __init__(self, label: str, ftype: str,
                 value: str, field_id: str, parent=None):
        super().__init__(parent)
        self.field_id = field_id
        self._ftype   = ftype
        self._build_ui(label, ftype, value)

    def _build_ui(self, label: str, ftype: str, value: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(4)

        # ── 标题行：字段名 + 类型标签 + 操作按钮
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        self.label_input = QLineEdit(label)
        self.label_input.setPlaceholderText("字段名称")
        self.label_input.setFixedHeight(32)
        self.label_input.setStyleSheet("font-size: 12px; padding: 6px 10px;")
        header_row.addWidget(self.label_input, stretch=1)

        type_lbl = QLabel(FIELD_TYPE_LABELS.get(ftype, ftype))
        type_lbl.setProperty("class", "hint")
        type_lbl.setFixedHeight(32)
        header_row.addWidget(type_lbl)

        # 上移 / 下移 / 删除
        for icon_name, signal in [
            ("chevron-up",   self.move_up_requested),
            ("chevron-down", self.move_down_requested),
        ]:
            btn = QPushButton()
            btn.setProperty("class", "icon-btn")
            btn.setFixedSize(26, 26)
            btn.setIcon(_icon(icon_name, color="#6a6a6a", size=13))
            btn.setIconSize(QSize(13, 13))
            btn.clicked.connect(lambda _, s=signal: s.emit(self.field_id))
            header_row.addWidget(btn)

        del_btn = QPushButton()
        del_btn.setProperty("class", "icon-btn")
        del_btn.setFixedSize(26, 26)
        del_btn.setIcon(_icon("x", color="#6a6a6a", size=13))
        del_btn.setIconSize(QSize(13, 13))
        del_btn.setToolTip("删除此字段")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.field_id))
        header_row.addWidget(del_btn)

        root.addLayout(header_row)

        # ── 值输入区（根据类型不同）
        self._value_widget = self._make_value_widget(ftype, value)
        root.addWidget(self._value_widget)

        # 分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        root.addWidget(sep)

    def _make_value_widget(self, ftype: str, value: str) -> QWidget:
        """根据字段类型创建对应的值输入控件。"""
        if ftype == "secret":
            return _SecretInput(value)

        elif ftype == "date":
            w = QLineEdit(value)
            w.setPlaceholderText("YYYY-MM-DD，如 2026-12-31")
            w.setMinimumHeight(36)
            return w

        elif ftype == "date_domain":
            # 拆分 "域名|到期日"
            if "|" in value:
                domain, expire = value.split("|", 1)
            else:
                domain, expire = value, ""

            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            self._domain_input = QLineEdit(domain.strip())
            self._domain_input.setPlaceholderText("域名，如 example.com")
            self._domain_input.setMinimumHeight(36)
            row.addWidget(self._domain_input, stretch=2)

            self._expire_input = QLineEdit(expire.strip())
            self._expire_input.setPlaceholderText("到期日 YYYY-MM-DD")
            self._expire_input.setMinimumHeight(36)
            row.addWidget(self._expire_input, stretch=1)

            return container

        else:  # text
            w = QLineEdit(value)
            w.setPlaceholderText("请输入值...")
            w.setMinimumHeight(36)
            return w

    # ── 读取值接口

    def get_label(self) -> str:
        return self.label_input.text().strip()

    def get_type(self) -> str:
        return self._ftype

    def get_value(self) -> str:
        """返回当前字段值（明文）。"""
        ftype = self._ftype

        if ftype == "secret":
            return self._value_widget.get_value()

        elif ftype == "date_domain":
            domain = self._domain_input.text().strip()
            expire = self._expire_input.text().strip()
            if domain or expire:
                return f"{domain}|{expire}"
            return ""

        elif isinstance(self._value_widget, QLineEdit):
            return self._value_widget.text().strip()

        return ""


# ─────────────────────────────────────────────
# Secret 输入控件（密码框 + 显示/隐藏切换）
# ─────────────────────────────────────────────

class _SecretInput(QWidget):
    """带显示/隐藏切换的密码输入框。"""

    def __init__(self, value: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.input = QLineEdit(value)
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("输入值（保存时自动加密）")
        self.input.setMinimumHeight(36)
        layout.addWidget(self.input, stretch=1)

        self._visible = False
        self.toggle_btn = QPushButton()
        self.toggle_btn.setProperty("class", "icon-btn")
        self.toggle_btn.setFixedSize(36, 36)
        self.toggle_btn.setIcon(_icon("eye", color="#6a6a6a", size=15))
        self.toggle_btn.setIconSize(QSize(15, 15))
        self.toggle_btn.setToolTip("显示/隐藏")
        self.toggle_btn.clicked.connect(self._toggle)
        layout.addWidget(self.toggle_btn)

        self.gen_btn = QPushButton()
        self.gen_btn.setProperty("class", "icon-btn")
        self.gen_btn.setFixedSize(36, 36)
        self.gen_btn.setIcon(_icon("key", color="#6a6a6a", size=15))
        self.gen_btn.setIconSize(QSize(15, 15))
        self.gen_btn.setToolTip("生成随机密码")
        self.gen_btn.clicked.connect(self._do_generate)
        layout.addWidget(self.gen_btn)

    def _do_generate(self):
        """打开密码生成器对话框，确认后把生成的密码填入输入框。"""
        dlg = _PasswordGeneratorDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.input.setText(dlg.get_password())

    def _toggle(self):
        self._visible = not self._visible
        self.input.setEchoMode(
            QLineEdit.Normal if self._visible else QLineEdit.Password
        )
        if self._visible:
            self.toggle_btn.setIcon(_icon("eye-off", color="#f5a623", size=15))
            self.toggle_btn.setToolTip("隐藏")
        else:
            self.toggle_btn.setIcon(_icon("eye", color="#6a6a6a", size=15))
            self.toggle_btn.setToolTip("显示")

    def get_value(self) -> str:
        return self.input.text()


# ─────────────────────────────────────────────
# 密码生成器对话框
# ─────────────────────────────────────────────

class _PasswordGeneratorDialog(QDialog):
    """随机密码生成器：长度 + 字符类选项，确认后回填 secret 输入框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生成密码")
        self.setFixedSize(380, 300)
        self._password = ""
        self._build_ui()
        self._regenerate()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        # 长度
        len_row = QHBoxLayout()
        len_lbl = QLabel("长度")
        len_lbl.setProperty("class", "field-label")
        len_row.addWidget(len_lbl)
        self.length_spin = QSpinBox()
        self.length_spin.setRange(8, 64)
        self.length_spin.setValue(16)
        self.length_spin.setMinimumHeight(30)
        self.length_spin.setSuffix(" 位")
        len_row.addWidget(self.length_spin, stretch=1)
        layout.addLayout(len_row)

        # 字符类选项（小写字母始终包含）
        self.chk_upper = QCheckBox("大写字母 (A-Z)")
        self.chk_digits = QCheckBox("数字 (0-9)")
        self.chk_symbols = QCheckBox("符号 (!@#$%^&*-_=+?)")
        self.chk_unambiguous = QCheckBox("排除易混淆字符 (0/O/o、1/l/I)")
        for chk in (self.chk_upper, self.chk_digits,
                    self.chk_symbols, self.chk_unambiguous):
            chk.setChecked(True)
            layout.addWidget(chk)

        # 预览（只读、可选中手动复制）
        prev_row = QHBoxLayout()
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(36)
        prev_row.addWidget(self.preview, stretch=1)

        copy_btn = QPushButton()
        copy_btn.setProperty("class", "icon-btn")
        copy_btn.setFixedSize(36, 36)
        copy_btn.setIcon(_icon("copy", color="#6a6a6a", size=14))
        copy_btn.setIconSize(QSize(14, 14))
        copy_btn.setToolTip("复制到剪贴板")
        copy_btn.clicked.connect(self._do_copy)
        prev_row.addWidget(copy_btn)
        layout.addLayout(prev_row)

        layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        regen_btn = QPushButton("  换一个")
        regen_btn.setProperty("class", "ghost")
        regen_btn.setIcon(_icon("refresh", color="#b3b3b3", size=14))
        regen_btn.setIconSize(QSize(14, 14))
        regen_btn.clicked.connect(self._regenerate)
        btn_row.addWidget(regen_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        use_btn = QPushButton("  使用此密码")
        use_btn.setProperty("class", "primary")
        use_btn.clicked.connect(self.accept)
        btn_row.addWidget(use_btn)
        layout.addLayout(btn_row)

        # 控件全部建完再连信号：setChecked(True) 会触发 toggled，
        # 若预览控件尚不存在会崩溃
        self.length_spin.valueChanged.connect(self._regenerate)
        for chk in (self.chk_upper, self.chk_digits,
                    self.chk_symbols, self.chk_unambiguous):
            chk.toggled.connect(self._regenerate)

    def _regenerate(self):
        """按当前选项生成新密码并显示。"""
        try:
            self._password = generate_password(
                self.length_spin.value(),
                upper=self.chk_upper.isChecked(),
                digits=self.chk_digits.isChecked(),
                symbols=self.chk_symbols.isChecked(),
                avoid_ambiguous=self.chk_unambiguous.isChecked(),
            )
            self.preview.setText(self._password)
        except ValueError:
            # 选项组合非法时清空等待调整（长度 8..64 时理论上不会发生）
            self._password = ""
            self.preview.setText("")

    def _do_copy(self):
        if not self._password:
            return
        # 必须捕获当前密码值：定时器触发时 _password 可能已被重新生成
        pwd = self._password
        QApplication.clipboard().setText(pwd)
        from ui.entry_detail import (
            note_clipboard_copy, _clear_clipboard_if_matches,
            CLIPBOARD_CLEAR_SECONDS,
        )
        note_clipboard_copy(pwd)
        QTimer.singleShot(
            CLIPBOARD_CLEAR_SECONDS * 1000,
            lambda p=pwd: _clear_clipboard_if_matches(p),
        )

    def get_password(self) -> str:
        """返回当前生成的密码（点击"使用此密码"后由调用方读取）。"""
        return self._password


# ─────────────────────────────────────────────
# 添加字段对话框
# ─────────────────────────────────────────────


class _AddFieldDialog(QDialog):
    """添加新字段时弹出：输入字段名称，选择字段类型。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加字段")
        self.setFixedSize(320, 240)
        self._result = ("", "text")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(QLabel("字段名称"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如：密保问题、恢复码、手机号")
        self.name_input.returnPressed.connect(self._accept_if_valid)
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("字段类型"))
        self.type_combo = QComboBox()
        for ftype, label in FIELD_TYPES:
            self.type_combo.addItem(label, ftype)
        layout.addWidget(self.type_combo)

        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.setProperty("class", "ghost")
        cancel.clicked.connect(self.reject)

        ok = QPushButton("添加")
        ok.setProperty("class", "primary")
        ok.clicked.connect(self._accept_if_valid)

        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self.name_input.setFocus()

    def _accept_if_valid(self):
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setPlaceholderText("请输入字段名称！")
            return
        self._result = (name, self.type_combo.currentData())
        self.accept()

    def get_result(self) -> tuple:
        """返回 (label, field_type)。"""
        return self._result
