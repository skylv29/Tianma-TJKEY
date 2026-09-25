# ui/export_dialog.py
# TJKEY 导出对话框
#
# 流程：
#   1. 弹出二级密码验证
#   2. 验证通过后选择保存路径
#   3. 生成 Markdown 文件（secret 字段用代码块，结构按分类层级）

import os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QFrame, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, QSize
from icons import icon as _icon

from session import session
from accounts import load_accounts, verify_export_password
from crypto import decrypt_field, is_encrypted, field_aad
from markdown_export import build_markdown, restrict_file_permissions


# 进行中的导出 worker 注册表：锁屏/退出时统一取消，
# 防止后台线程持有 session_key 副本在锁屏后继续写出明文
_active_workers: set = set()


def cancel_active_exports() -> None:
    """取消所有进行中的导出任务（锁屏与关窗时调用）。"""
    for worker in list(_active_workers):
        worker.cancel()


# ─────────────────────────────────────────────
# 后台导出工作线程
# ─────────────────────────────────────────────

class _ExportWorker(QObject):
    """在后台线程生成 Markdown 文件（解密所有 secret 字段可能耗时）。"""
    finished = Signal(str)   # 成功，携带输出路径
    error    = Signal(str)   # 失败/取消，携带错误信息

    def __init__(self, vault_data: dict, session_key: bytes, output_path: str):
        super().__init__()
        self._vault_data   = vault_data
        self._session_key  = session_key
        self._output_path  = output_path
        self._cancelled    = False

    def cancel(self):
        """请求取消导出（写盘前后均会检查该标志）。"""
        self._cancelled = True

    def _should_abort(self) -> bool:
        return self._cancelled or session.is_locked()

    def run(self):
        try:
            if self._should_abort():
                self.error.emit("导出已取消")
                return
            content = _build_markdown(self._vault_data, self._session_key)
            if self._should_abort():
                self.error.emit("导出已取消")
                return
            # 原子写：先写 .tmp 再替换，中断时不会留下半截明文文件
            tmp_path = self._output_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            restrict_file_permissions(tmp_path)
            os.replace(tmp_path, self._output_path)
            restrict_file_permissions(self._output_path)
            if self._should_abort():
                # 写盘期间被锁屏：删除刚落盘的明文文件
                try:
                    os.remove(self._output_path)
                except OSError:
                    pass
                self.error.emit("导出已取消")
                return
            self.finished.emit(self._output_path)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            _active_workers.discard(self)


# ─────────────────────────────────────────────
# Markdown 生成（共享实现在 markdown_export.py）
# ─────────────────────────────────────────────

def _build_decrypted_copy(vault_data: dict, session_key: bytes) -> dict:
    """返回 secret 字段已解密的 vault 深拷贝（解密失败的字段标记为占位文本）。"""
    result = copy.deepcopy(vault_data)
    for entry in result.get("entries", []):
        for field in entry.get("fields", []):
            value = field.get("value", "")
            if is_encrypted(value):
                try:
                    field["value"] = decrypt_field(
                        value, session_key,
                        aad=field_aad(result, entry.get("id"),
                                      field.get("id")))
                except Exception:
                    field["value"] = "（解密失败）"
    return result


def _build_markdown(vault_data: dict, session_key: bytes) -> str:
    """将 vault 数据解密后导出为 Markdown（与 recover.py 产出保持一致）。"""
    return build_markdown(_build_decrypted_copy(vault_data, session_key))


# ─────────────────────────────────────────────
# 导出对话框
# ─────────────────────────────────────────────

class ExportDialog(QDialog):
    """
    导出对话框。
    步骤：输入二级密码 → 验证 → 选择路径 → 后台生成文件。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出数据")
        self.setFixedSize(400, 300)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._thread = None
        self._worker = None
        self._loading = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        # 标题（图标 + 文字）
        from PySide6.QtWidgets import QHBoxLayout as _HBox
        from icons import pixmap as _px
        title_row = _HBox()
        title_row.setSpacing(10)
        title_row.setContentsMargins(0, 0, 0, 0)
        t_icon = QLabel()
        t_icon.setPixmap(_px("upload", color="#f5a623", size=20))
        t_icon.setFixedSize(20, 20)
        t_icon.setScaledContents(True)
        title_row.addWidget(t_icon)
        title = QLabel("导出明文数据")
        title.setProperty("class", "title")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        warn = QLabel(
            "导出文件将包含所有字段的明文内容（含密码）。\n"
            "请输入导出密码以继续。"
        )
        warn.setProperty("class", "hint")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        layout.addWidget(QLabel("导出密码"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setPlaceholderText("输入导出专用密码...")
        self.pwd_input.returnPressed.connect(self._do_verify)
        layout.addWidget(self.pwd_input)

        self.error_lbl = QLabel("")
        self.error_lbl.setProperty("class", "danger")
        self.error_lbl.setMinimumHeight(18)
        layout.addWidget(self.error_lbl)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        layout.addStretch()

        btn_row = QHBoxLayout()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setProperty("class", "ghost")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        btn_row.addStretch()

        self.export_btn = QPushButton("验证并导出")
        self.export_btn.setProperty("class", "primary")
        self.export_btn.clicked.connect(self._do_verify)
        btn_row.addWidget(self.export_btn)

        layout.addLayout(btn_row)

        self.pwd_input.setFocus()

    def _do_verify(self):
        """验证导出密码。"""
        pwd = self.pwd_input.text()
        if not pwd:
            self.error_lbl.setText("请输入导出密码")
            return

        try:
            accounts_data = load_accounts(session.myVault_path)
        except Exception as e:
            self.error_lbl.setText(f"读取账户配置失败：{e}")
            return

        if not verify_export_password(accounts_data,
                                      session.current_account, pwd):
            self.error_lbl.setText("导出密码错误，请重试")
            self.pwd_input.clear()
            self.pwd_input.setFocus()
            return

        # 验证通过立即清空导出密码，后续选路径/等待期间不留在输入框
        self.pwd_input.clear()

        # 密码验证通过，选择保存路径
        self._do_choose_path()

    def _do_choose_path(self):
        """弹出文件保存对话框。"""
        account  = session.current_account
        date_str = datetime.now().strftime("%Y%m%d")
        default_name = f"{account}_export_{date_str}.md"

        path, _ = QFileDialog.getSaveFileName(
            self, "选择导出路径",
            os.path.join(os.path.expanduser("~"), default_name),
            "Markdown 文件 (*.md);;所有文件 (*)"
        )
        if not path:
            return

        self._start_export(path)

    def _start_export(self, output_path: str):
        """在后台线程生成导出文件。"""
        self._set_loading(True)

        self._thread = QThread()
        self._worker = _ExportWorker(
            session.vault_data, session.session_key, output_path
        )
        _active_workers.add(self._worker)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_export_done)
        self._worker.error.connect(self._on_export_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _on_export_done(self, path: str):
        self._set_loading(False)
        # 信号排队期间可能已锁屏：删除明文文件并静默关闭
        if session.is_locked():
            try:
                os.remove(path)
            except OSError:
                pass
            self.reject()
            return
        QMessageBox.information(
            self, "导出成功",
            f"文件已保存到：\n{path}\n\n"
            "⚠️  此文件包含所有明文密码，请妥善保管，阅后建议删除。"
        )
        self.accept()

    def _on_export_error(self, msg: str):
        self._set_loading(False)
        # 锁屏导致的取消：不弹窗，直接关闭对话框
        if session.is_locked() or msg == "导出已取消":
            self.reject()
            return
        QMessageBox.warning(self, "导出失败", f"生成文件时出错：\n{msg}")

    def _set_loading(self, loading: bool):
        self._loading = loading
        self.export_btn.setEnabled(not loading)
        self.cancel_btn.setEnabled(not loading)
        self.pwd_input.setEnabled(not loading)
        self.progress.setVisible(loading)
        self.export_btn.setText("导出中..." if loading else "验证并导出")

    def reject(self):
        """导出进行中禁止通过取消按钮/ESC 关闭。"""
        if self._loading:
            return
        super().reject()

    def closeEvent(self, event):
        """导出进行中禁止通过窗口 X 关闭。"""
        if self._loading:
            event.ignore()
            return
        super().closeEvent(event)
