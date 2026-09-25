# ui/change_password_dialog.py
# 修改登录密码对话框（设置页面入口）
#
# 流程：
#   验证当前密码 → 输入并确认新密码 → 调 accounts.change_password()
#   （内部会用新密码重新加密 vault，两遍式处理，中断可自愈）
#
# 成功后当前会话的密钥已经作废（vault 已用新密码重加密），
# 必须强制锁屏回登录界面，让用户用新密码重新登录。

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from icons import icon as _icon, pixmap as _pixmap

from session import session
from accounts import load_accounts, verify_login, change_password
from vault_io import VaultReencryptError


class ChangePasswordDialog(QDialog):
    """修改登录密码对话框。

    发射信号：无。成功后依次关闭自身、父窗口（设置对话框），
    并触发主窗口锁屏回登录界面。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改登录密码")
        self.setFixedWidth(420)   # 高度自适应，固定高度会裁剪警告文字与按钮
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        # 标题
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        t_icon = QLabel()
        t_icon.setPixmap(_pixmap("lock", color="#f5a623", size=20))
        t_icon.setFixedSize(20, 20)
        t_icon.setScaledContents(True)
        title_row.addWidget(t_icon)
        title = QLabel("修改登录密码")
        title.setProperty("class", "title")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        account_lbl = QLabel(
            f"账号：{session.current_display_name or session.current_account}")
        account_lbl.setProperty("class", "hint")
        layout.addWidget(account_lbl)

        layout.addSpacing(4)

        layout.addWidget(self._field_label("当前密码"))
        self.old_input = QLineEdit()
        self.old_input.setEchoMode(QLineEdit.Password)
        self.old_input.setMinimumHeight(34)
        layout.addWidget(self.old_input)

        layout.addWidget(self._field_label("新密码"))
        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.Password)
        self.new_input.setMinimumHeight(34)
        self.new_input.setPlaceholderText("至少 8 位，建议混合字符类型")
        layout.addWidget(self.new_input)

        layout.addWidget(self._field_label("确认新密码"))
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setMinimumHeight(34)
        self.confirm_input.returnPressed.connect(self._do_change)
        layout.addWidget(self.confirm_input)

        self.error_lbl = QLabel("")
        self.error_lbl.setProperty("class", "danger")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setMinimumHeight(18)
        layout.addWidget(self.error_lbl)

        warn = QLabel(
            "确认修改后，该账号的数据文件将立即用新密码重新加密，"
            "并返回登录界面。请牢记新密码——忘记后只能用 recover.py "
            "配合旧密码抢救数据。")
        warn.setProperty("class", "hint")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        self.ok_btn = QPushButton("  确认修改")
        self.ok_btn.setProperty("class", "primary")
        self.ok_btn.setIcon(_icon("check", color="#121212", size=14))
        self.ok_btn.clicked.connect(self._do_change)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        self.old_input.setFocus()

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "field-label")
        return lbl

    def _show_error(self, msg: str):
        self.error_lbl.setText(msg)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def _do_change(self):
        old_pwd = self.old_input.text()
        new_pwd = self.new_input.text()
        confirm = self.confirm_input.text()

        if not old_pwd:
            self._show_error("请输入当前密码")
            return
        if not new_pwd:
            self._show_error("请输入新密码")
            return
        if len(new_pwd) < 8:
            self._show_error("新密码至少需要 8 位")
            return
        if new_pwd != confirm:
            self._show_error("两次输入的新密码不一致")
            return
        if new_pwd == old_pwd:
            self._show_error("新密码与当前密码相同")
            return

        # 验证当前密码（给出准确的错误信息，而不是笼统的"修改失败"）
        try:
            accounts_data = load_accounts(session.myVault_path)
        except Exception as e:
            self._show_error(f"读取账户配置失败：{e}")
            return
        if not verify_login(accounts_data, session.current_account, old_pwd):
            self._show_error("当前密码错误")
            self.old_input.clear()
            self.old_input.setFocus()
            return

        self._set_loading(True)
        try:
            ok = change_password(session.myVault_path,
                                 session.current_account, old_pwd, new_pwd)
        except VaultReencryptError as e:
            self._set_loading(False)
            QMessageBox.warning(
                self, "修改失败",
                f"数据文件与密码不匹配或已损坏，未做任何修改：\n{e}")
            return
        except Exception as e:
            self._set_loading(False)
            QMessageBox.warning(self, "修改失败", f"修改失败：{e}")
            return
        self._set_loading(False)

        if not ok:
            self._show_error("当前密码错误")
            return

        QMessageBox.information(
            self, "修改成功",
            "登录密码已修改，数据文件已用新密码重新加密。\n\n"
            "请使用新密码重新登录。")
        self.accept()

        # 关闭设置对话框（模态链上的父窗口）
        parent = self.parent()
        if parent is not None and hasattr(parent, "reject"):
            parent.reject()

        # 当前会话的密钥已随重加密作废，强制回登录界面
        main_window = session.main_window
        if main_window is not None:
            main_window._do_lock()
        else:
            session.lock()

    def _set_loading(self, loading: bool):
        self.ok_btn.setEnabled(not loading)
        self.old_input.setEnabled(not loading)
        self.new_input.setEnabled(not loading)
        self.confirm_input.setEnabled(not loading)
        self.ok_btn.setText("修改中..." if loading else "  确认修改")
