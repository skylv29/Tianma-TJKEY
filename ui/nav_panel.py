# ui/nav_panel.py
# TJKEY 左侧分类导航面板
#
# 功能：
#   - 显示两级分类树（大类 → 小类）
#   - 支持拖拽排序（大类上下、小类上下、小类跨大类）
#   - 右键菜单：新建、重命名、删除
#   - 固定项：所有条目、未分类
#   - 点击分类时发射 category_selected 信号

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QMenu, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QPoint, QSize

from session import session
from ui.vault_sync import save_vault_or_lock
from icons import icon as _icon, pixmap as _pixmap
from vault_io import (
    add_category, add_subcategory,
    rename_category, rename_subcategory,
    delete_category, delete_subcategory,
    move_subcategory,
    reorder_categories, reorder_subcategories,
    get_entries_by_category,
)


# ── 特殊节点 ID
NAV_ALL       = "__all__"
NAV_UNCAT     = "__uncat__"
NAV_DELETED   = "__deleted__"


class NavPanel(QFrame):
    """
    左侧分类导航面板。

    发射的信号：
        category_selected(cat_id, sub_id)
            cat_id: 大类 ID / NAV_ALL / NAV_UNCAT
            sub_id: 小类 ID / None
        categories_changed()
            分类结构发生变化（增删改排序），通知列表面板刷新
    """
    category_selected = Signal(str, object)   # (cat_id, sub_id|None)
    categories_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "nav-panel")
        self.setMinimumWidth(160)
        self.setMaximumWidth(280)

        self._current_cat_id = NAV_ALL
        self._current_sub_id = None
        self._drag_source_item = None   # 拖拽源节点

        self._build_ui()

    # ─────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题
        header = QLabel("  分类导航")
        header.setProperty("class", "section-header")
        header.setFixedHeight(36)
        layout.addWidget(header)

        # 分类树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)

        # 拖拽支持
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)

        # 覆盖拖放事件
        self.tree.dropEvent = self._tree_drop_event

        layout.addWidget(self.tree)

        # 分隔线
        sep = QFrame()
        sep.setProperty("class", "separator")
        layout.addWidget(sep)

        # 固定项（所有条目 / 未分类）
        fixed_widget = QWidget()
        fixed_layout = QVBoxLayout(fixed_widget)
        fixed_layout.setContentsMargins(8, 4, 8, 4)
        fixed_layout.setSpacing(2)

        self.btn_all     = _NavButton("layers", "所有条目", NAV_ALL)
        self.btn_uncat   = _NavButton("inbox",  "未分类",   NAV_UNCAT)
        self.btn_deleted = _NavButton("trash",  "回收站",   NAV_DELETED)
        self.btn_all.clicked_nav.connect(self._on_fixed_clicked)
        self.btn_uncat.clicked_nav.connect(self._on_fixed_clicked)
        self.btn_deleted.clicked_nav.connect(self._on_fixed_clicked)

        fixed_layout.addWidget(self.btn_all)
        fixed_layout.addWidget(self.btn_uncat)
        fixed_layout.addWidget(self.btn_deleted)
        layout.addWidget(fixed_widget)

        # 底部新建大类按钮
        new_cat_btn = _IconTextLabel("plus", "新建大类",
                                       icon_color="#6a6a6a", text_color="#6a6a6a",
                                       icon_size=13)
        new_cat_btn.setFixedHeight(32)
        new_cat_btn.setAlignment(Qt.AlignCenter)
        new_cat_btn.setCursor(Qt.PointingHandCursor)
        new_cat_btn.mousePressEvent = lambda e: self._create_category()
        layout.addWidget(new_cat_btn)

    # ─────────────────────────────────────────
    # 数据刷新
    # ─────────────────────────────────────────

    def refresh(self):
        """从 session.vault_data 重新加载分类树，保持当前选中状态。"""
        current_cat = self._current_cat_id
        current_sub = self._current_sub_id

        self.tree.blockSignals(True)
        self.tree.clear()

        if not session.vault_data:
            self.tree.blockSignals(False)
            return

        categories = sorted(
            session.vault_data.get("categories", []),
            key=lambda c: c.get("order", 0)
        )

        for cat in categories:
            cat_item = QTreeWidgetItem(self.tree)
            cat_item.setText(0, f"  {cat['name']}")
            cat_item.setIcon(0, _icon("folder", color="#b3b3b3", size=16))
            cat_item.setData(0, Qt.UserRole, {"type": "cat", "id": cat["id"]})
            cat_item.setFlags(
                cat_item.flags()
                | Qt.ItemIsDropEnabled
                | Qt.ItemIsDragEnabled
            )

            subs = sorted(
                cat.get("subcategories", []),
                key=lambda s: s.get("order", 0)
            )
            for sub in subs:
                sub_item = QTreeWidgetItem(cat_item)
                sub_item.setText(0, f"  {sub['name']}")
                sub_item.setIcon(0, _icon("folder", color="#6a6a6a", size=14))
                sub_item.setData(0, Qt.UserRole, {
                    "type": "sub",
                    "id": sub["id"],
                    "parent_id": cat["id"],
                })
                sub_item.setFlags(
                    sub_item.flags()
                    | Qt.ItemIsDragEnabled
                )
                # 恢复选中
                if current_cat == cat["id"] and current_sub == sub["id"]:
                    self.tree.setCurrentItem(sub_item)

            cat_item.setExpanded(True)

            # 恢复大类选中
            if current_cat == cat["id"] and current_sub is None:
                self.tree.setCurrentItem(cat_item)

        self.tree.blockSignals(False)

        # 恢复固定项高亮
        self._update_fixed_highlight()

    def _update_fixed_highlight(self):
        """根据当前选中状态更新固定按钮高亮。"""
        self.btn_all.set_selected(self._current_cat_id == NAV_ALL)
        self.btn_uncat.set_selected(self._current_cat_id == NAV_UNCAT)
        self.btn_deleted.set_selected(self._current_cat_id == NAV_DELETED)

    # ─────────────────────────────────────────
    # 点击事件
    # ─────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        self.btn_all.set_selected(False)
        self.btn_uncat.set_selected(False)
        self.btn_deleted.set_selected(False)

        if data["type"] == "cat":
            self._current_cat_id = data["id"]
            self._current_sub_id = None
            self.category_selected.emit(data["id"], None)

        elif data["type"] == "sub":
            self._current_cat_id = data["parent_id"]
            self._current_sub_id = data["id"]
            self.category_selected.emit(data["parent_id"], data["id"])

    def _on_fixed_clicked(self, nav_id: str):
        self.tree.clearSelection()
        self._current_cat_id = nav_id
        self._current_sub_id = None
        self._update_fixed_highlight()
        self.category_selected.emit(nav_id, None)

    def select_all(self):
        """外部调用：切换到"所有条目"视图。"""
        self._on_fixed_clicked(NAV_ALL)

    # ─────────────────────────────────────────
    # 右键菜单
    # ─────────────────────────────────────────

    def _show_context_menu(self, pos: QPoint):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            # 点击空白区域
            menu.addAction("新建大类", self._create_category)
        else:
            data = item.data(0, Qt.UserRole)
            if not data:
                return

            if data["type"] == "cat":
                menu.addAction("新建子类", lambda: self._create_subcategory(data["id"]))
                menu.addSeparator()
                menu.addAction("重命名", lambda: self._rename_category(data["id"], item))
                menu.addSeparator()
                act_del = menu.addAction("删除大类", lambda: self._delete_category(data["id"]))
                act_del.setIcon(self.style().standardIcon(
                    self.style().StandardPixmap.SP_TrashIcon))

            elif data["type"] == "sub":
                menu.addAction("重命名", lambda: self._rename_subcategory(data["id"], item))
                menu.addSeparator()
                act_del = menu.addAction("删除子类", lambda: self._delete_subcategory(data["id"]))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ─────────────────────────────────────────
    # 分类 CRUD
    # ─────────────────────────────────────────

    def _create_category(self):
        name, ok = QInputDialog.getText(self, "新建大类", "请输入大类名称：")
        if not ok or not name.strip():
            return
        if not self._mutate_and_save(
                lambda: add_category(session.vault_data, name.strip())):
            return
        self.categories_changed.emit()

    def _create_subcategory(self, parent_id: str):
        name, ok = QInputDialog.getText(self, "新建子类", "请输入子类名称：")
        if not ok or not name.strip():
            return
        if not self._mutate_and_save(
                lambda: add_subcategory(session.vault_data, parent_id,
                                        name.strip())):
            return
        self.categories_changed.emit()

    def _rename_category(self, cat_id: str, item: QTreeWidgetItem):
        current = item.text(0).strip()
        name, ok = QInputDialog.getText(
            self, "重命名大类", "请输入新名称：", text=current)
        if not ok or not name.strip() or name.strip() == current:
            return
        if not self._mutate_and_save(
                lambda: rename_category(session.vault_data, cat_id,
                                        name.strip())):
            return
        self.categories_changed.emit()

    def _rename_subcategory(self, sub_id: str, item: QTreeWidgetItem):
        current = item.text(0).strip()
        name, ok = QInputDialog.getText(
            self, "重命名子类", "请输入新名称：", text=current)
        if not ok or not name.strip() or name.strip() == current:
            return
        if not self._mutate_and_save(
                lambda: rename_subcategory(session.vault_data, sub_id,
                                           name.strip())):
            return
        self.categories_changed.emit()

    def _delete_category(self, cat_id: str):
        # 统计受影响条目数
        all_entries = get_entries_by_category(session.vault_data, cat_id)
        count = len(all_entries)

        if count > 0:
            msg = (f"该大类下共有 {count} 个条目。\n"
                   "删除后这些条目将移入「未分类」。\n\n确认删除？")
        else:
            msg = "确认删除该大类？"

        reply = QMessageBox.question(
            self, "删除大类", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # 如果当前选中的是被删除的分类，切换到"所有条目"
        prev_sel = None
        if self._current_cat_id == cat_id:
            prev_sel = (self._current_cat_id, self._current_sub_id)
            self._current_cat_id = NAV_ALL
            self._current_sub_id = None
            self.category_selected.emit(NAV_ALL, None)

        if not self._mutate_and_save(
                lambda: delete_category(session.vault_data, cat_id)):
            # 保存失败回滚内存后，恢复原选中状态
            if prev_sel and not session.is_locked():
                self._current_cat_id, self._current_sub_id = prev_sel
                self.category_selected.emit(*prev_sel)
            return
        self.categories_changed.emit()

    def _delete_subcategory(self, sub_id: str):
        from vault_io import get_entries_by_category
        # 找属于该子类的条目
        entries = [e for e in session.vault_data.get("entries", [])
                   if e.get("subcategory_id") == sub_id]
        count = len(entries)

        if count > 0:
            msg = (f"该子类下共有 {count} 个条目。\n"
                   "删除后这些条目将移入父大类（无子类）。\n\n确认删除？")
        else:
            msg = "确认删除该子类？"

        reply = QMessageBox.question(
            self, "删除子类", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        prev_sub = self._current_sub_id if self._current_sub_id == sub_id else None

        if not self._mutate_and_save(
                lambda: delete_subcategory(session.vault_data, sub_id)):
            return

        if prev_sub is not None:
            self._current_sub_id = None
            self.category_selected.emit(self._current_cat_id, None)

        self.categories_changed.emit()

    # ─────────────────────────────────────────
    # 拖拽排序
    # ─────────────────────────────────────────

    def _tree_drop_event(self, event):
        """
        自定义拖放处理，支持：
          - 大类之间上下排序
          - 小类在同大类内排序
          - 小类拖入另一个大类
        """
        target_item = self.tree.itemAt(event.position().toPoint())
        dragged_item = self.tree.currentItem()

        if dragged_item is None:
            event.ignore()
            return

        dragged_data = dragged_item.data(0, Qt.UserRole)
        if not dragged_data:
            event.ignore()
            return

        # ── 大类拖拽排序
        if dragged_data["type"] == "cat":
            if target_item is None or target_item.data(0, Qt.UserRole) is None:
                event.ignore()
                return
            target_data = target_item.data(0, Qt.UserRole)
            if target_data["type"] != "cat":
                event.ignore()
                return
            # 执行排序
            self._reorder_cats_by_drag(dragged_data["id"], target_data["id"])
            event.acceptProposedAction()
            return

        # ── 小类拖拽
        if dragged_data["type"] == "sub":
            if target_item is None:
                event.ignore()
                return

            target_data = target_item.data(0, Qt.UserRole)
            if not target_data:
                event.ignore()
                return

            if target_data["type"] == "cat":
                # 拖到大类节点上 → 移入该大类末尾
                new_parent_id = target_data["id"]
                if new_parent_id != dragged_data["parent_id"]:
                    ok = self._mutate_and_save(
                        lambda: move_subcategory(
                            session.vault_data, dragged_data["id"],
                            new_parent_id))
                    if not ok:
                        event.ignore()
                        return
                    self.categories_changed.emit()
                event.acceptProposedAction()
                return

            elif target_data["type"] == "sub":
                # 拖到另一个小类节点上
                if target_data["parent_id"] == dragged_data["parent_id"]:
                    # 同大类内排序
                    self._reorder_subs_by_drag(
                        dragged_data["parent_id"],
                        dragged_data["id"],
                        target_data["id"]
                    )
                else:
                    # 不同大类，移入目标小类所在大类
                    ok = self._mutate_and_save(
                        lambda: move_subcategory(
                            session.vault_data, dragged_data["id"],
                            target_data["parent_id"]))
                    if not ok:
                        event.ignore()
                        return
                    self.categories_changed.emit()
                event.acceptProposedAction()
                return

        event.ignore()

    def _reorder_cats_by_drag(self, dragged_id: str, target_id: str):
        """将被拖拽的大类移动到目标大类的位置。"""
        cats = session.vault_data.get("categories", [])
        ids = [c["id"] for c in sorted(cats, key=lambda c: c.get("order", 0))]

        if dragged_id not in ids or target_id not in ids:
            return

        ids.remove(dragged_id)
        target_idx = ids.index(target_id)
        ids.insert(target_idx, dragged_id)

        if not self._mutate_and_save(
                lambda: reorder_categories(session.vault_data, ids)):
            return
        self.categories_changed.emit()

    def _reorder_subs_by_drag(self, parent_id: str, dragged_id: str, target_id: str):
        """在同一大类内将被拖拽的小类移动到目标小类的位置。"""
        from vault_io import get_category_by_id
        parent = get_category_by_id(session.vault_data, parent_id)
        if not parent:
            return

        subs = parent.get("subcategories", [])
        ids = [s["id"] for s in sorted(subs, key=lambda s: s.get("order", 0))]

        if dragged_id not in ids or target_id not in ids:
            return

        ids.remove(dragged_id)
        target_idx = ids.index(target_id)
        ids.insert(target_idx, dragged_id)

        if not self._mutate_and_save(
                lambda: reorder_subcategories(session.vault_data, parent_id,
                                              ids)):
            return
        self.categories_changed.emit()

    # ─────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────

    def _mutate_and_save(self, mutate_fn) -> bool:
        """对 session.vault_data 执行 mutate_fn 后保存；失败时回滚内存。

        背景：分类操作先改内存再保存，写盘失败（磁盘满等）若不回滚，
        会出现"界面显示新结构、磁盘仍是旧结构"的分叉。
        外部修改触发强制锁屏时会话已清空，无需回滚。
        """
        import copy as _copy
        snapshot = _copy.deepcopy(session.vault_data)
        mutate_fn()
        if not save_vault_or_lock():
            if not session.is_locked() and snapshot is not None:
                session.vault_data.clear()
                session.vault_data.update(snapshot)
            return False
        self.refresh()
        return True

    def get_current_selection(self) -> tuple:
        """返回当前选中的 (cat_id, sub_id)。"""
        return self._current_cat_id, self._current_sub_id


# ─────────────────────────────────────────────
# 固定导航按钮（所有条目 / 未分类）
# ─────────────────────────────────────────────

class _NavButton(QWidget):
    """
    左侧导航区的固定按钮（所有条目、未分类）。
    图标 + 文字横排，点击时发射 clicked_nav(nav_id) 信号。
    """
    clicked_nav = Signal(str)

    def __init__(self, icon_name: str, text: str, nav_id: str, parent=None):
        super().__init__(parent)
        self.nav_id = nav_id
        self._icon_name = icon_name
        self._text = text
        self._selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(8)

        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(16, 16)
        self._icon_lbl.setScaledContents(True)
        layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(text)
        layout.addWidget(self._text_lbl, stretch=1)

        self._apply_style()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _apply_style(self):
        from styles import color
        if self._selected:
            bg = color("bg_selected")
            fg = color("text_primary")
            ic = color("accent")
        else:
            bg = "transparent"
            fg = color("text_secondary")
            ic = color("text_secondary")

        self.setStyleSheet(
            f"QWidget {{ background-color: {bg}; border-radius: 6px; }}"
        )
        self._text_lbl.setStyleSheet(
            f"QLabel {{ color: {fg}; font-size: 13px; background: transparent; }}"
        )
        self._icon_lbl.setPixmap(_pixmap(self._icon_name, color=ic, size=16))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked_nav.emit(self.nav_id)
        super().mousePressEvent(event)


class _IconTextLabel(QWidget):
    """图标+文字水平排列的 Label（用于新建大类按钮）。"""

    def __init__(self, icon_name: str, text: str,
                 icon_color: str = "#6a6a6a",
                 text_color: str = "#6a6a6a",
                 icon_size: int = 14,
                 parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(_pixmap(icon_name, color=icon_color, size=icon_size))
        icon_lbl.setFixedSize(icon_size, icon_size)
        icon_lbl.setScaledContents(True)
        layout.addWidget(icon_lbl)

        text_lbl = QLabel(text)
        text_lbl.setStyleSheet(
            f"color: {text_color}; font-size: 12px; background: transparent;"
        )
        layout.addWidget(text_lbl)

    def setAlignment(self, alignment):
        pass  # 兼容外部调用，由内部布局控制对齐
