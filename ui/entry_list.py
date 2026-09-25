# ui/entry_list.py
# TJKEY 中间条目列表面板
#
# 功能：
#   - 顶部实时搜索栏
#   - 按分类/搜索词显示条目卡片列表
#   - 点击条目发射 entry_selected 信号
#   - 右键菜单：删除、移动到分类
#   - 条目间拖拽排序（grabMouse 机制）
#   - 新建条目触发模板选择弹窗

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QFrame, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QScrollArea,
    QMenu, QMessageBox, QDialog, QListWidget,
    QListWidgetItem,
    QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer, QPoint, QSize
from PySide6.QtGui import QColor
import shiboken6
from icons import icon as _icon, pixmap as _pixmap

from session import session
from ui.vault_sync import save_vault_or_lock
from vault_io import (
    get_entries_by_category, search_entries,
    delete_entry, restore_entry, purge_entry, get_deleted_entries,
    get_category_by_id, get_subcategory_by_id,
    reorder_entries, build_entry_from_template,
    add_entry,
)

NAV_ALL   = "__all__"
NAV_UNCAT = "__uncat__"
NAV_DELETED = "__deleted__"


class EntryCard(QFrame):
    """
    条目列表中的单张卡片。

    显示：条目名称 + 分类路径/摘要（回收站视图附加删除时间）
    交互：点击选中、右键菜单（普通视图：编辑/移动/删除；
          回收站视图：恢复/永久删除）
    """
    clicked           = Signal(str)
    delete_requested  = Signal(str)
    move_requested    = Signal(str)
    restore_requested = Signal(str)
    purge_requested   = Signal(str)
    drag_initiated    = Signal(str, object)  # entry_id, global_pos

    def __init__(self, entry: dict, vault_data: dict,
                 parent=None, deleted_view: bool = False):
        super().__init__(parent)
        self.entry_id    = entry["id"]
        self._entry      = entry
        self._vault_data = vault_data
        self._deleted_view = deleted_view
        self._selected   = False
        self._press_pos  = None

        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 12, 9)
        layout.setSpacing(3)

        name = self._entry.get("name", "（未命名）")
        self.name_lbl = QLabel(name)
        self.name_lbl.setProperty("class", "entry-name")
        layout.addWidget(self.name_lbl)

        meta_text = self._make_meta()
        if self._deleted_view:
            del_at = self._entry.get("deleted_at", "")
            del_str = (f"删除于 {del_at[:16].replace('T', ' ')}  ·  "
                       if del_at else "已删除  ·  ")
            meta_text = del_str + meta_text
        self.meta_lbl = QLabel(meta_text)
        self.meta_lbl.setProperty("class", "entry-meta")
        self.meta_lbl.setWordWrap(False)
        layout.addWidget(self.meta_lbl)

    def _make_meta(self) -> str:
        parts = []

        cat_id = self._entry.get("category_id")
        sub_id = self._entry.get("subcategory_id")

        if cat_id:
            cat = get_category_by_id(self._vault_data, cat_id)
            if cat:
                if sub_id:
                    _, sub = get_subcategory_by_id(self._vault_data, sub_id)
                    if sub:
                        parts.append(f"{cat['name']} › {sub['name']}")
                    else:
                        parts.append(cat["name"])
                else:
                    parts.append(cat["name"])

        domain_fields = [
            f for f in self._entry.get("fields", [])
            if f.get("type") == "date_domain" and f.get("value")
        ]
        if domain_fields:
            domain_count = len(domain_fields)
            if domain_count == 1:
                val = domain_fields[0]["value"]
                domain_name = val.split("|")[0].strip() if "|" in val else val
                parts.append(domain_name)
            else:
                parts.append(f"{domain_count} 个域名")

        tags = self._entry.get("tags", [])
        if tags:
            parts.append("  ".join(f"#{t}" for t in tags[:3]))

        return "  ·  ".join(parts) if parts else "无分类"

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        from styles import color
        if self._selected:
            bg          = color("bg_selected")
            left_border = f"3px solid {color('accent')}"
            right_border = f"1px solid {color('accent')}"
            top_border   = f"1px solid {color('accent')}"
            bot_border   = f"1px solid {color('accent')}"
        else:
            bg           = "transparent"
            left_border  = "3px solid transparent"
            right_border = "1px solid transparent"
            top_border   = "1px solid transparent"
            bot_border   = "1px solid transparent"

        hover_bg     = color("bg_hover")
        hover_left   = f"3px solid {color('accent')}"
        hover_border = f"1px solid {color('border')}"

        self.setStyleSheet(
            f"EntryCard {{"
            f"  background-color: {bg};"
            f"  border-top: {top_border};"
            f"  border-right: {right_border};"
            f"  border-bottom: {bot_border};"
            f"  border-left: {left_border};"
            f"  border-radius: 8px;"
            f"}}"
            f"EntryCard:hover {{"
            f"  background-color: {hover_bg};"
            f"  border-top: {hover_border};"
            f"  border-right: {hover_border};"
            f"  border-bottom: {hover_border};"
            f"  border-left: {hover_left};"
            f"  border-radius: 8px;"
            f"}}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self.clicked.emit(self.entry_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None
                and event.buttons() & Qt.LeftButton):
            distance = (event.pos() - self._press_pos).manhattanLength()
            if distance > QApplication.startDragDistance():
                global_pos = self.mapToGlobal(event.pos())
                self.drag_initiated.emit(self.entry_id, global_pos)
                self._press_pos = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def _show_menu(self, pos: QPoint):
        menu = QMenu(self)

        if self._deleted_view:
            act_restore = menu.addAction("  恢复")
            act_restore.setIcon(_icon("refresh", color="#1ed760", size=14))
            act_restore.triggered.connect(
                lambda: self.restore_requested.emit(self.entry_id))
            menu.addSeparator()
            act_purge = menu.addAction("  永久删除")
            act_purge.setIcon(_icon("trash", color="#f3727f", size=14))
            act_purge.triggered.connect(
                lambda: self.purge_requested.emit(self.entry_id))
            menu.exec(self.mapToGlobal(pos))
            return

        act_edit = menu.addAction("  编辑")
        act_edit.setIcon(_icon("edit", color="#b3b3b3", size=14))
        act_edit.triggered.connect(lambda: self.clicked.emit(self.entry_id))

        act_move = menu.addAction("  移动到分类")
        act_move.setIcon(_icon("folder", color="#b3b3b3", size=14))
        act_move.triggered.connect(
            lambda: self.move_requested.emit(self.entry_id))
        menu.addSeparator()
        act_del = menu.addAction("  删除（移入回收站）")
        act_del.setIcon(_icon("trash", color="#f3727f", size=14))
        act_del.triggered.connect(
            lambda: self.delete_requested.emit(self.entry_id)
        )

        menu.exec(self.mapToGlobal(pos))


class EntryListPanel(QFrame):
    """
    中间条目列表面板。

    发射信号：
        entry_selected(entry_id)
        entry_deleted(entry_id)
        new_entry_requested(tpl_id, cat_id, sub_id)
    """
    entry_selected     = Signal(str)
    entry_deleted      = Signal(str)
    new_entry_requested = Signal(str, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "list-panel")
        self.setMinimumWidth(220)

        self._current_cat_id = NAV_ALL
        self._current_sub_id = None
        self._current_entry_id: str | None = None
        self._search_query = ""
        self._entries_shown: list = []

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._apply_search)

        self._drag_active = False
        self._drag_source_id = None
        self._drag_source_idx = -1
        self._drag_target_idx = -1
        self._drag_placeholder = None
        self._drag_last_target = -1

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        search_bar = QFrame()
        search_bar.setFixedHeight(48)
        search_layout = QHBoxLayout(search_bar)
        search_layout.setContentsMargins(10, 8, 10, 8)
        search_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setProperty("class", "search")
        self.search_input.setPlaceholderText("🔍  搜索账号...")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        root.addWidget(search_bar)

        sep = QFrame()
        sep.setProperty("class", "separator")
        root.addWidget(sep)

        self.cat_header = QLabel("所有条目")
        self.cat_header.setProperty("class", "section-header")
        self.cat_header.setFixedHeight(32)
        root.addWidget(self.cat_header)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(6, 4, 6, 4)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()

        self._scroll_area.setWidget(self.list_container)
        root.addWidget(self._scroll_area, stretch=1)

        self.empty_lbl = QLabel("暂无条目\n\n点击底部「+ 新建条目」添加")
        self.empty_lbl.setProperty("class", "hint")
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setVisible(False)
        root.addWidget(self.empty_lbl)

    def load_category(self, cat_id: str, sub_id=None):
        self._current_cat_id = cat_id
        self._current_sub_id = sub_id

        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self._search_query = ""

        self.cat_header.setText(self._make_header_text(cat_id, sub_id))
        self._refresh_list()

    def _make_header_text(self, cat_id: str, sub_id) -> str:
        if cat_id == NAV_ALL:
            return "  所有条目"
        if cat_id == NAV_UNCAT:
            return "  未分类"
        if cat_id == NAV_DELETED:
            return "  回收站"
        if not session.vault_data:
            return "  条目"

        cat = get_category_by_id(session.vault_data, cat_id)
        cat_name = cat["name"] if cat else "未知分类"

        if sub_id:
            _, sub = get_subcategory_by_id(session.vault_data, sub_id)
            sub_name = sub["name"] if sub else "未知子类"
            return f"  {cat_name}  ›  {sub_name}"
        return f"  {cat_name}"

    def _refresh_list(self):
        if not session.vault_data:
            self._entries_shown = []
            self._render_entries([])
            return

        if self._search_query:
            entries = search_entries(session.vault_data, self._search_query)
        else:
            sub_arg = self._current_sub_id if self._current_sub_id else ...
            if self._current_cat_id == NAV_ALL:
                entries = get_entries_by_category(session.vault_data, NAV_ALL)
            elif self._current_cat_id == NAV_UNCAT:
                entries = get_entries_by_category(session.vault_data, None)
            elif self._current_cat_id == NAV_DELETED:
                entries = get_deleted_entries(session.vault_data)
            else:
                entries = get_entries_by_category(
                    session.vault_data,
                    self._current_cat_id,
                    sub_arg,
                )

        self._entries_shown = entries
        self._render_entries(entries)

    def _render_entries(self, entries: list):
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.empty_lbl.setVisible(len(entries) == 0)
        self.list_container.setVisible(len(entries) > 0)

        for entry in entries:
            in_deleted = self._current_cat_id == NAV_DELETED
            card = EntryCard(entry, session.vault_data, deleted_view=in_deleted)
            card.clicked.connect(self._on_card_clicked)
            card.delete_requested.connect(self._on_delete_requested)
            card.move_requested.connect(self._on_move_requested)
            card.drag_initiated.connect(self._on_drag_initiated)
            if in_deleted:
                card.restore_requested.connect(self._on_restore_requested)
                card.purge_requested.connect(self._on_purge_requested)

            if entry["id"] == self._current_entry_id:
                card.set_selected(True)

            self.list_layout.insertWidget(
                self.list_layout.count() - 1, card
            )

    def _on_search_changed(self, text: str):
        self._search_query = text.strip()
        if self._search_query:
            self.cat_header.setText("  搜索结果")
        else:
            self.cat_header.setText(
                self._make_header_text(self._current_cat_id, self._current_sub_id)
            )
        self._search_timer.start()

    def _apply_search(self):
        self._refresh_list()

    def _on_card_clicked(self, entry_id: str):
        self._current_entry_id = entry_id
        self._update_selection()
        self.entry_selected.emit(entry_id)

    def _update_selection(self):
        for i in range(self.list_layout.count() - 1):
            item = self.list_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, EntryCard):
                    card.set_selected(card.entry_id == self._current_entry_id)

    def _on_delete_requested(self, entry_id: str):
        entry = next(
            (e for e in session.vault_data.get("entries", [])
             if e["id"] == entry_id), None
        )
        name = entry["name"] if entry else "该条目"

        reply = QMessageBox.question(
            self, "移入回收站",
            f"确认将「{name}」移入回收站？\n可稍后在回收站中恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if not self._mutate_and_save(
                lambda: delete_entry(session.vault_data, entry_id)):
            return

        if self._current_entry_id == entry_id:
            self._current_entry_id = None

        self._refresh_list()
        self.entry_deleted.emit(entry_id)

    def _on_restore_requested(self, entry_id: str):
        """回收站视图：恢复条目到原分类。"""
        if not self._mutate_and_save(
                lambda: restore_entry(session.vault_data, entry_id)):
            return
        if self._current_entry_id == entry_id:
            self._current_entry_id = None
        self._refresh_list()
        # 复用 entry_deleted 通知主窗口刷新计数与到期提醒
        self.entry_deleted.emit(entry_id)

    def _on_purge_requested(self, entry_id: str):
        """回收站视图：永久删除条目（不可恢复）。"""
        entry = next(
            (e for e in session.vault_data.get("entries", [])
             if e["id"] == entry_id), None
        )
        name = entry["name"] if entry else "该条目"

        reply = QMessageBox.question(
            self, "永久删除",
            f"确认永久删除「{name}」？\n此操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 快照原条目：写盘失败时回滚内存中的永久删除
        orig_purge = None
        raw = next(
            (e for e in session.vault_data.get("entries", [])
             if e["id"] == entry_id), None
        )
        if raw is not None:
            import copy as _copy
            orig_purge = _copy.deepcopy(raw)

        purge_entry(session.vault_data, entry_id)
        if not self._save():
            # 写盘出错：回滚内存中的永久删除（外部锁屏时会话已清空，无需回滚）
            if not session.is_locked() and orig_purge is not None:
                entries = session.vault_data.get("entries", [])
                for i, e in enumerate(entries):
                    if e.get("id") == entry_id:
                        entries[i] = orig_purge
                        break
            return
        if self._current_entry_id == entry_id:
            self._current_entry_id = None
        self._refresh_list()
        self.entry_deleted.emit(entry_id)

    def _on_move_requested(self, entry_id: str):
        dlg = _MoveToCategoryDialog(entry_id, session.vault_data, self)
        if dlg.exec() == QDialog.Accepted:
            new_cat_id, new_sub_id = dlg.get_result()
            entry = next(
                (e for e in session.vault_data.get("entries", [])
                 if e["id"] == entry_id), None
            )
            if entry:
                same_cat = [
                    e for e in session.vault_data.get("entries", [])
                    if e.get("category_id") == new_cat_id and e["id"] != entry_id
                ]
                max_order = max((e.get("order", 0) for e in same_cat), default=-1)

                def _move():
                    entry["category_id"]    = new_cat_id
                    entry["subcategory_id"] = new_sub_id
                    entry["order"]          = max_order + 1

                if not self._mutate_and_save(_move):
                    return
                self._refresh_list()
                self._current_entry_id = None

    def show_new_entry_dialog(self):
        if not session.vault_data:
            return
        if self._current_cat_id == NAV_DELETED:
            return   # 回收站视图不提供新建入口

        dlg = _TemplateSelectDialog(session.vault_data, self)
        if dlg.exec() == QDialog.Accepted:
            tpl_id = dlg.get_selected_template_id()
            self.new_entry_requested.emit(
                tpl_id,
                self._current_cat_id if self._current_cat_id not in (NAV_ALL, NAV_UNCAT) else None,
                self._current_sub_id,
            )

    def refresh(self):
        self._refresh_list()

    def clear_selection(self):
        """清除条目选中状态（锁屏/重新登录时调用，避免跨会话残留选中）。"""
        self._current_entry_id = None

    def select_entry(self, entry_id: str):
        self._current_entry_id = entry_id
        self._update_selection()

        for i in range(self.list_layout.count() - 1):
            item = self.list_layout.itemAt(i)
            if item and item.widget():
                card = item.widget()
                if isinstance(card, EntryCard) and card.entry_id == entry_id:
                    QTimer.singleShot(50, lambda c=card: self._scroll_to(c))
                    break

    def _scroll_to(self, widget: QWidget):
        # 50ms 延时期间列表可能已刷新销毁该卡片，直接访问会抛
        # RuntimeError: Internal C++ object already deleted——先校验对象存活
        if not shiboken6.isValid(widget):
            return
        self._scroll_area.ensureWidgetVisible(widget)

    # ─────────────────────────────────────────
    # 拖拽排序（grabMouse 机制）
    # ─────────────────────────────────────────

    def _get_all_cards(self):
        cards = []
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), EntryCard):
                cards.append(item.widget())
        return cards

    def _on_drag_initiated(self, entry_id: str, global_pos: QPoint):
        if self._drag_active:
            return

        if self._current_cat_id in (NAV_ALL, NAV_DELETED):
            return

        cards = self._get_all_cards()
        source_idx = -1
        for i, card in enumerate(cards):
            if card.entry_id == entry_id:
                source_idx = i
                break

        if source_idx < 0:
            return

        self._drag_active = True
        self._drag_source_id = entry_id
        self._drag_source_idx = source_idx
        self._drag_target_idx = source_idx
        self._drag_last_target = -1

        self._search_timer.stop()

        cards[source_idx].setVisible(False)

        self._drag_placeholder = QFrame()
        self._drag_placeholder.setFixedHeight(56)
        self._drag_placeholder.setStyleSheet(
            "QFrame {"
            "  background-color: rgba(245,166,35,0.12);"
            "  border: 2px dashed #f5a623;"
            "  border-radius: 8px;"
            "}"
        )
        self.list_layout.insertWidget(source_idx, self._drag_placeholder)

        self.grabMouse()
        self._drag_update_target(global_pos)

    def _drag_update_target(self, global_pos: QPoint):
        if not self._drag_active:
            return

        local_pos = self.list_container.mapFromGlobal(global_pos)
        cards = self._get_all_cards()
        visible = [c for c in cards if c.isVisible()]

        target = len(visible)
        for idx, card in enumerate(visible):
            rect = card.geometry()
            mid = rect.top() + rect.height() / 2
            if local_pos.y() < mid:
                target = idx
                break

        self._drag_target_idx = target

        if target == self._drag_last_target:
            return
        self._drag_last_target = target

        if not self._drag_placeholder:
            return

        self.list_layout.removeWidget(self._drag_placeholder)

        if target >= len(visible):
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._drag_placeholder)
        else:
            target_card = visible[target]
            layout_idx = self.list_layout.indexOf(target_card)
            self.list_layout.insertWidget(layout_idx, self._drag_placeholder)

    def _drag_finish(self):
        if not self._drag_active:
            return

        self.releaseMouse()

        source_idx = self._drag_source_idx
        target_idx = self._drag_target_idx
        source_id = self._drag_source_id

        self._drag_cleanup()

        if source_idx != target_idx:
            if not self._do_reorder(source_idx, target_idx):
                # 保存失败：不按内存中的新顺序刷新，避免 UI 与磁盘不一致
                return

        self._refresh_list()

        if source_id:
            QTimer.singleShot(50, lambda eid=source_id: self.select_entry(eid))

    def _drag_cancel(self):
        if not self._drag_active:
            return
        self.releaseMouse()
        self._drag_cleanup()
        self._refresh_list()

    def _drag_cleanup(self):
        if self._drag_placeholder:
            self.list_layout.removeWidget(self._drag_placeholder)
            self._drag_placeholder.deleteLater()
            self._drag_placeholder = None

        cards = self._get_all_cards()
        for card in cards:
            card.setVisible(True)

        self._drag_active = False
        self._drag_source_id = None
        self._drag_source_idx = -1
        self._drag_target_idx = -1
        self._drag_last_target = -1

    def mouseMoveEvent(self, event):
        if self._drag_active:
            self._drag_update_target(event.globalPos())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_active and event.button() == Qt.LeftButton:
            self._drag_finish()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._drag_active and event.key() == Qt.Key_Escape:
            self._drag_cancel()
            return
        super().keyPressEvent(event)

    def _do_reorder(self, source_idx: int, target_idx: int) -> bool:
        if (not session.vault_data or len(self._entries_shown) <= 1
                or self._current_cat_id in (NAV_ALL, NAV_DELETED)):
            return True

        import copy as _copy
        snapshot = _copy.deepcopy(session.vault_data)

        entries_list = list(self._entries_shown)
        if source_idx < 0 or source_idx >= len(entries_list):
            return True
        if target_idx < 0 or target_idx > len(entries_list):
            return True

        moved_entry = entries_list.pop(source_idx)
        entries_list.insert(target_idx, moved_entry)

        new_order_ids = [entry["id"] for entry in entries_list]

        if self._current_cat_id == NAV_UNCAT:
            for i, eid in enumerate(new_order_ids):
                entry = next(
                    (e for e in session.vault_data.get("entries", [])
                     if e["id"] == eid), None
                )
                if entry:
                    entry["order"] = i
        elif self._current_sub_id:
            for i, eid in enumerate(new_order_ids):
                entry = next(
                    (e for e in session.vault_data.get("entries", [])
                     if e["id"] == eid), None
                )
                if entry:
                    entry["order"] = i
        else:
            reorder_entries(session.vault_data, self._current_cat_id, new_order_ids)

        if not self._save():
            # 写盘失败：回滚内存顺序，保持与磁盘一致
            # （外部修改锁屏时会话已清空，无需回滚）
            if not session.is_locked() and snapshot is not None:
                session.vault_data.clear()
                session.vault_data.update(snapshot)
            return False
        return True

    def _save(self) -> bool:
        """保存 vault；返回 False 表示失败，调用方应中止后续刷新与信号。"""
        return save_vault_or_lock()

    def _mutate_and_save(self, mutate_fn) -> bool:
        """执行 mutate_fn 后保存；写盘失败时回滚内存，保持界面/磁盘一致。"""
        import copy as _copy
        snapshot = _copy.deepcopy(session.vault_data)
        mutate_fn()
        if not save_vault_or_lock():
            if not session.is_locked() and snapshot is not None:
                session.vault_data.clear()
                session.vault_data.update(snapshot)
            return False
        return True


class _TemplateSelectDialog(QDialog):
    def __init__(self, vault_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择模板")
        self.setFixedSize(340, 400)
        self._vault_data = vault_data
        self._selected_id = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("选择条目模板")
        title.setProperty("class", "title")
        layout.addWidget(title)

        hint = QLabel("选择一个模板作为新条目的字段结构起点")
        hint.setProperty("class", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.itemDoubleClicked.connect(self._accept)
        layout.addWidget(self.list_widget)

        templates = self._vault_data.get("templates", [])
        builtin   = [t for t in templates if t.get("is_builtin")]
        custom    = [t for t in templates if not t.get("is_builtin")]

        if builtin:
            sep_item = QListWidgetItem("── 内置模板 ──")
            sep_item.setFlags(Qt.NoItemFlags)
            sep_item.setForeground(QColor("#6c7086"))
            self.list_widget.addItem(sep_item)

        for tpl in builtin:
            item = QListWidgetItem(f"  {tpl['name']}")
            item.setData(Qt.UserRole, tpl["id"])
            field_types = [f["type"] for f in tpl.get("fields", [])]
            secret_n = field_types.count("secret")
            item.setToolTip(
                f"字段数：{len(tpl['fields'])}  "
                f"（其中 {secret_n} 个加密字段）"
            )
            self.list_widget.addItem(item)

        if custom:
            sep_item2 = QListWidgetItem("── 自定义模板 ──")
            sep_item2.setFlags(Qt.NoItemFlags)
            sep_item2.setForeground(QColor("#6c7086"))
            self.list_widget.addItem(sep_item2)

            for tpl in custom:
                item = QListWidgetItem(f"  ⭐  {tpl['name']}")
                item.setData(Qt.UserRole, tpl["id"])
                self.list_widget.addItem(item)

        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.UserRole):
                self.list_widget.setCurrentItem(it)
                break

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "ghost")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("选择")
        ok_btn.setProperty("class", "primary")
        ok_btn.clicked.connect(self._accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _accept(self):
        item = self.list_widget.currentItem()
        if item and item.data(Qt.UserRole):
            self._selected_id = item.data(Qt.UserRole)
            self.accept()

    def get_selected_template_id(self) -> str | None:
        return self._selected_id


class _MoveToCategoryDialog(QDialog):
    def __init__(self, entry_id: str, vault_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("移动到分类")
        self.setFixedSize(300, 380)
        self._vault_data = vault_data
        self._entry_id   = entry_id
        self._result: tuple = (None, None)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("移动到分类")
        title.setProperty("class", "title")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._accept)
        layout.addWidget(self.list_widget)

        item = QListWidgetItem("  未分类")
        item.setIcon(_icon("inbox", color="#6a6a6a", size=15))
        item.setData(Qt.UserRole, (None, None))
        self.list_widget.addItem(item)

        categories = sorted(
            self._vault_data.get("categories", []),
            key=lambda c: c.get("order", 0)
        )
        for cat in categories:
            cat_item = QListWidgetItem(f"  {cat['name']}")
            cat_item.setData(Qt.UserRole, (cat["id"], None))
            cat_item.setIcon(_icon("folder", color="#b3b3b3", size=15))
            self.list_widget.addItem(cat_item)

            subs = sorted(
                cat.get("subcategories", []),
                key=lambda s: s.get("order", 0)
            )
            for sub in subs:
                sub_item = QListWidgetItem(f"      {sub['name']}")
                sub_item.setData(Qt.UserRole, (cat["id"], sub["id"]))
                sub_item.setIcon(_icon("folder", color="#6a6a6a", size=13))
                self.list_widget.addItem(sub_item)

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "ghost")
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("确认移动")
        ok_btn.setProperty("class", "primary")
        ok_btn.clicked.connect(self._accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _accept(self):
        item = self.list_widget.currentItem()
        if item:
            self._result = item.data(Qt.UserRole)
            self.accept()

    def get_result(self) -> tuple:
        return self._result
