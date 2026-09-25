# ui/login.py
# TJKEY 登录界面 + 首次启动引导
#
# 包含两个窗口：
#   SetupWizard  - 首次启动时引导用户选择 MyVault 文件夹
#   LoginWindow  - 主登录界面，含账号输入、密码输入、登录逻辑
#
# 登录成功后不直接打开主窗口，而是发射 login_success 信号，
# 由 main.py 监听并完成后续操作（派生密钥、加载 vault、打开主窗口）。

import os
import sys
import re

from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog,
    QApplication, QMessageBox, QProgressBar,
    QDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer, QSize, QEventLoop
from PySide6.QtGui import QKeyEvent
from icons import icon as _icon, pixmap as _pixmap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session import session
from version import APP_NAME, APP_VERSION
from accounts import (
    read_app_config, write_app_config,
    load_accounts, load_app_conf,
    get_default_username, get_account,
    verify_login, get_vault_path,
    get_accounts_path, AccountsFormatError,
    create_account, init_readme,
)
from vault_io import (
    load_vault, VaultFormatError, detect_conflict_files,
    find_first_encrypted_field, migrate_aad_format, file_sha256,
    create_empty_vault,
)
from crypto import (
    derive_key, decrypt_field, DecryptError, field_aad, KDF_ITERATIONS,
)


# ─────────────────────────────────────────────
# 密钥派生工作线程（避免 UI 卡顿）
# ─────────────────────────────────────────────

class DeriveKeyWorker(QObject):
    """
    在后台线程派生 AES 密钥（PBKDF2 需要约 0.3-1 秒）。
    完成后发射 finished 信号，失败时发射 error 信号。
    """
    finished = Signal(bytes)   # 派生成功，携带密钥
    error = Signal(str)        # 派生失败，携带错误消息

    def __init__(self, password: str, salt_b64: str,
                 iterations: int = KDF_ITERATIONS):
        super().__init__()
        self.password = password
        self.salt_b64 = salt_b64
        self.iterations = iterations

    def run(self):
        try:
            key = derive_key(self.password, self.salt_b64, self.iterations)
        except Exception as e:
            self.error.emit(str(e))
            return
        finally:
            # 尽早释放明文密码的引用（Python 字符串无法主动擦除，
            # 只能尽快解除引用交给 GC）
            self.password = ""
            self.salt_b64 = ""
        self.finished.emit(key)


# ─────────────────────────────────────────────
# 首次启动引导窗口
# ─────────────────────────────────────────────

class SetupWizard(QWidget):
    """
    首次启动（或 app.config 丢失/路径失效）时显示的引导窗口。
    引导用户选择 MyVault 数据文件夹，并检查其中是否有 accounts.conf。
    成功后发射 setup_done 信号，携带已验证的 myVault_path。
    """
    setup_done = Signal(str)   # 配置完成，携带 myVault_path
    closed = Signal()          # 窗口被关闭（无论是否确认完成）

    def __init__(self, app_dir: str):
        super().__init__()
        self.app_dir = app_dir
        self.selected_path = ""
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("TJKEY — 初始设置")
        self.setFixedWidth(520)   # 高度自适应，固定高度会裁剪底部按钮
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        _set_window_icon(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 主卡片
        card = QFrame()
        card.setProperty("class", "login-card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(20)
        card_layout.setContentsMargins(40, 40, 40, 40)

        # 标题（图标 + 文字）
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignCenter)
        title_row.setSpacing(12)
        title_icon = QLabel()
        title_icon.setPixmap(_pixmap("lock", color="#f5a623", size=28))
        title_icon.setFixedSize(28, 28)
        title_icon.setScaledContents(True)
        title_row.addWidget(title_icon)
        title_lbl = QLabel("TJKEY 初始设置")
        title_lbl.setProperty("class", "app-title")
        title_row.addWidget(title_lbl)
        card_layout.addLayout(title_row)

        # 说明文字
        desc = QLabel(
            "欢迎使用 TJKEY！\n\n"
            "请选择您的数据文件夹（MyVault）所在位置。\n"
            "这个文件夹通常放在云盘同步目录中，\n"
            "以便在多台电脑之间自动同步数据。\n\n"
            "如果是第一次使用，请先创建一个空文件夹，\n"
            "然后运行 vault_admin.py 创建您的账号。"
        )
        desc.setProperty("class", "subtitle")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        # 路径选择行
        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("MyVault 文件夹路径...")
        self.path_input.setReadOnly(True)
        self.path_input.setMinimumHeight(40)
        path_row.addWidget(self.path_input)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(80)
        browse_btn.setMinimumHeight(40)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        card_layout.addLayout(path_row)

        # 状态提示
        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setMinimumHeight(36)
        card_layout.addWidget(self.status_lbl)

        # 首次建号（选中了有效文件夹但缺少 accounts.conf 时显示）
        self.create_btn = QPushButton("  创建第一个账号")
        self.create_btn.setProperty("class", "primary")
        self.create_btn.setFixedHeight(40)
        self.create_btn.setIcon(_icon("user", color="#121212", size=16))
        self.create_btn.setIconSize(QSize(16, 16))
        self.create_btn.setVisible(False)
        self.create_btn.clicked.connect(self._create_first_account)
        card_layout.addWidget(self.create_btn)

        # 确认按钮
        self.confirm_btn = QPushButton("确认并开始使用")
        self.confirm_btn.setProperty("class", "primary")
        self.confirm_btn.setFixedHeight(40)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)
        card_layout.addWidget(self.confirm_btn)

        root.addWidget(card)

    def _browse(self):
        """打开文件夹选择对话框。"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择 MyVault 数据文件夹",
            os.path.expanduser("~"),
        )
        if not path:
            return

        self.selected_path = path
        self.path_input.setText(path)
        self._validate_path(path)

    def _validate_path(self, path: str):
        """
        检查所选文件夹是否包含有效的 accounts.conf。
        根据结果更新状态提示和确认按钮状态。
        """
        accounts_conf = os.path.join(path, "accounts.conf")

        if not os.path.isfile(accounts_conf):
            # 新文件夹，没有 accounts.conf：提供应用内建号，
            # 不再要求用户去命令行运行 vault_admin.py
            self.status_lbl.setText(
                "⚠️  这是一个新的空文件夹。\n"
                "可以直接创建您的第一个账号（推荐），\n"
                "或先运行 vault_admin.py 再重开程序。"
            )
            self.status_lbl.setProperty("class", "warning")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            self.confirm_btn.setEnabled(False)
            self.create_btn.setVisible(True)
            return

        self.create_btn.setVisible(False)

        # 检查 accounts.conf 是否有效
        try:
            accounts_data = load_accounts(path)
            account_count = len(accounts_data.get("accounts", []))
            if account_count == 0:
                self.status_lbl.setText(
                    "⚠️  accounts.conf 中没有任何账号。\n"
                    "请运行 vault_admin.py 创建账号后重试。"
                )
                self.status_lbl.setProperty("class", "warning")
                self.confirm_btn.setEnabled(False)
            else:
                self.status_lbl.setText(
                    f"✅  检测到 {account_count} 个账号，文件夹验证通过！"
                )
                self.status_lbl.setProperty("class", "success")
                self.confirm_btn.setEnabled(True)
        except (FileNotFoundError, AccountsFormatError) as e:
            self.status_lbl.setText(f"❌  accounts.conf 格式错误：{e}")
            self.status_lbl.setProperty("class", "danger")
            self.confirm_btn.setEnabled(False)

        self.status_lbl.style().unpolish(self.status_lbl)
        self.status_lbl.style().polish(self.status_lbl)

    def _confirm(self):
        """确认路径，写入 app.config，发射 setup_done 信号。"""
        if not self.selected_path:
            return
        write_app_config(self.app_dir, self.selected_path)
        self.setup_done.emit(self.selected_path)
        self.close()

    def _create_first_account(self):
        """在当前选中的数据文件夹内创建第一个账号，成功后刷新状态。"""
        dlg = _CreateAccountDialog(self.selected_path, self)
        if dlg.exec() == QDialog.Accepted and dlg.created_username:
            self.status_lbl.setText(
                f"✅  账号「{dlg.created_username}」创建成功！\n"
                "点击下方按钮开始使用。")
            self.status_lbl.setProperty("class", "success")
            self.status_lbl.style().unpolish(self.status_lbl)
            self.status_lbl.style().polish(self.status_lbl)
            self.confirm_btn.setEnabled(True)

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()


# ─────────────────────────────────────────────
# 首次建号对话框（首次启动向导使用）
# ─────────────────────────────────────────────

class _CreateAccountDialog(QDialog):
    """
    创建第一个账号的表单（首次启动向导内嵌使用）。

    创建内容：
      accounts.conf 注册账号 + vaults/<username>.vault 空白数据文件
      + MyVault/README.txt 恢复说明。
    等价于 vault_admin.py 的"创建新账号"菜单，但面向首次使用的图形界面。
    """

    def __init__(self, myVault_path: str, parent=None):
        super().__init__(parent)
        self.myVault_path = myVault_path
        self.created_username = ""
        self.setWindowTitle("创建第一个账号")
        self.setFixedWidth(420)   # 高度自适应，表单字段较多
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(8)

        title = QLabel("创建第一个账号")
        title.setProperty("class", "title")
        layout.addWidget(title)

        hint = QLabel(
            "账号将创建在您选定的数据文件夹中。\n"
            "登录密码用于解锁数据；导出密码用于导出明文数据，\n建议两者不同。")
        hint.setProperty("class", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(self._lbl("用户名（字母/数字/下划线，如 main）"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("main")
        self.username_input.setMinimumHeight(34)
        layout.addWidget(self.username_input)

        layout.addWidget(self._lbl("显示名称（选填，默认同用户名）"))
        self.display_input = QLineEdit()
        self.display_input.setPlaceholderText("如 大号")
        self.display_input.setMinimumHeight(34)
        layout.addWidget(self.display_input)

        layout.addWidget(self._lbl("登录密码（至少 8 位）"))
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setMinimumHeight(34)
        layout.addWidget(self.pwd_input)

        layout.addWidget(self._lbl("确认登录密码"))
        self.pwd2_input = QLineEdit()
        self.pwd2_input.setEchoMode(QLineEdit.Password)
        self.pwd2_input.setMinimumHeight(34)
        layout.addWidget(self.pwd2_input)

        layout.addWidget(self._lbl("导出密码（至少 8 位）"))
        self.exp_input = QLineEdit()
        self.exp_input.setEchoMode(QLineEdit.Password)
        self.exp_input.setMinimumHeight(34)
        layout.addWidget(self.exp_input)

        layout.addWidget(self._lbl("确认导出密码"))
        self.exp2_input = QLineEdit()
        self.exp2_input.setEchoMode(QLineEdit.Password)
        self.exp2_input.setMinimumHeight(34)
        self.exp2_input.returnPressed.connect(self._do_create)
        layout.addWidget(self.exp2_input)

        self.error_lbl = QLabel("")
        self.error_lbl.setProperty("class", "danger")
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setMinimumHeight(18)
        layout.addWidget(self.error_lbl)

        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "ghost")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        self.ok_btn = QPushButton("  创建账号")
        self.ok_btn.setProperty("class", "primary")
        self.ok_btn.setIcon(_icon("check", color="#121212", size=14))
        self.ok_btn.clicked.connect(self._do_create)
        btn_row.addWidget(self.ok_btn)
        layout.addLayout(btn_row)

        self.username_input.setFocus()

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("class", "field-label")
        return lbl

    def _do_create(self):
        """校验表单并创建账号 + 空白数据文件。"""
        username = self.username_input.text().strip()
        display = self.display_input.text().strip() or username
        pwd = self.pwd_input.text()
        pwd2 = self.pwd2_input.text()
        exp = self.exp_input.text()
        exp2 = self.exp2_input.text()

        if not username:
            self.error_lbl.setText("请输入用户名")
            return
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            self.error_lbl.setText("用户名只能包含字母、数字和下划线")
            return
        if not pwd or not exp:
            self.error_lbl.setText("登录密码和导出密码都不能为空")
            return
        if len(pwd) < 8 or len(exp) < 8:
            self.error_lbl.setText("两种密码都至少需要 8 位")
            return
        if pwd != pwd2:
            self.error_lbl.setText("两次输入的登录密码不一致")
            return
        if exp != exp2:
            self.error_lbl.setText("两次输入的导出密码不一致")
            return

        self.ok_btn.setEnabled(False)
        try:
            create_account(self.myVault_path, username, display, pwd, exp)
        except ValueError as e:
            self.error_lbl.setText(str(e))
            self.ok_btn.setEnabled(True)
            return
        except Exception as e:
            self.error_lbl.setText(f"创建失败：{e}")
            self.ok_btn.setEnabled(True)
            return

        # 创建空白数据文件（失败不回滚账号注册，提示用 vault_admin 修复）
        try:
            vault_path = os.path.join(self.myVault_path,
                                      "vaults", f"{username}.vault")
            create_empty_vault(vault_path, username)
            init_readme(self.myVault_path)
        except Exception as e:
            QMessageBox.warning(
                self, "账号已创建",
                f"账号注册成功，但数据文件创建失败：{e}\n"
                "请运行 vault_admin.py 检查修复。")
            self.ok_btn.setEnabled(True)
            return

        self.created_username = username
        self.accept()


# ─────────────────────────────────────────────
# 登录窗口
# ─────────────────────────────────────────────

class LoginWindow(QWidget):
    """
    主登录界面。
    账号名默认预填 app.conf 中的 last_account（或 accounts.conf 的 default_account）。
    密码验证通过后在后台派生密钥，并用 vault 中的加密字段校验密钥
    （防止账户配置与数据文件错位），完成后发射 login_success 信号。
    """
    login_success = Signal()   # 登录完全成功（密钥已派生，vault 已加载）

    def __init__(self, myVault_path: str):
        super().__init__()
        self.myVault_path = myVault_path
        self._derive_thread = None
        self._derive_worker = None
        # username -> display_name 缓存：账号联想（textChanged）每次按键
        # 都会查询，不能每次都读磁盘上的 accounts.conf
        self._display_name_cache: dict = {}
        self._build_ui()
        self._load_defaults()

    # ── UI 构建

    def _build_ui(self):
        self.setWindowTitle("TJKEY")
        self.setFixedSize(400, 480)
        self.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)
        # 窗口图标
        _set_window_icon(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 垂直居中
        root.addStretch(1)

        # ── 登录卡片
        card = QFrame()
        card.setProperty("class", "login-card")
        card.setFixedWidth(340)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(32, 32, 32, 32)

        # Logo + 标题
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setPixmap(_pixmap("lock", color="#f5a623", size=48))
        logo_lbl.setFixedHeight(52)
        logo_lbl.setScaledContents(False)
        card_layout.addWidget(logo_lbl)

        title_lbl = QLabel("TJKEY")
        title_lbl.setProperty("class", "app-title")
        title_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_lbl)

        # 显示名称（动态更新）
        self.display_name_lbl = QLabel("")
        self.display_name_lbl.setProperty("class", "hint")
        self.display_name_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.display_name_lbl)

        card_layout.addSpacing(8)

        # 账号输入行
        acct_lbl = QLabel("账号")
        acct_lbl.setProperty("class", "field-label")
        card_layout.addWidget(acct_lbl)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入账号名...")
        self.username_input.setMinimumHeight(40)
        self.username_input.textChanged.connect(self._on_username_changed)
        card_layout.addWidget(self.username_input)

        # 密码输入行
        pwd_lbl = QLabel("密码")
        pwd_lbl.setProperty("class", "field-label")
        card_layout.addWidget(pwd_lbl)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("输入登录密码...")
        self.password_input.setMinimumHeight(40)
        self.password_input.returnPressed.connect(self._do_login)
        card_layout.addWidget(self.password_input)

        # 错误提示
        self.error_lbl = QLabel("")
        self.error_lbl.setProperty("class", "danger")
        self.error_lbl.setAlignment(Qt.AlignCenter)
        self.error_lbl.setWordWrap(True)
        self.error_lbl.setMinimumHeight(20)
        card_layout.addWidget(self.error_lbl)

        # 进度条（派生密钥时显示）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # 不确定进度（滚动动画）
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setVisible(False)
        card_layout.addWidget(self.progress_bar)

        # 登录按钮
        self.login_btn = QPushButton("登 录")
        self.login_btn.setProperty("class", "primary")
        self.login_btn.setFixedHeight(40)
        self.login_btn.clicked.connect(self._do_login)
        card_layout.addWidget(self.login_btn)

        # 居中卡片
        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(card)
        center_row.addStretch()
        root.addLayout(center_row)

        root.addStretch(1)

        # 底部版本号
        ver_lbl = QLabel(f"{APP_NAME}  v{APP_VERSION}")
        ver_lbl.setProperty("class", "hint")
        ver_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(ver_lbl)
        root.addSpacing(12)

    # ── 初始化默认值

    def _load_defaults(self):
        """从 app.conf 和 accounts.conf 加载默认账号名并预填。"""
        try:
            app_conf = load_app_conf(self.myVault_path)
            last = app_conf.get("last_account", "")

            accounts_data = load_accounts(self.myVault_path)
            default = get_default_username(accounts_data)

            # 预热显示名称缓存（登录阶段唯一一次读盘，
            # 之后账号联想的每次按键都只查内存）
            for acc in accounts_data.get("accounts", []):
                self._display_name_cache[acc.get("username", "")] = \
                    acc.get("display_name", "")

            # 优先用上次登录的账号，否则用默认账号
            prefill = last if last else default
            if prefill:
                self.username_input.setText(prefill)
                self._update_display_name(prefill)

        except Exception:
            pass   # 配置读取失败时静默处理，不影响界面显示

        # 焦点给密码框（账号名已预填）
        if self.username_input.text():
            self.password_input.setFocus()
        else:
            self.username_input.setFocus()

    # ── 账号名变化时更新显示名称

    def _on_username_changed(self, text: str):
        """账号名输入框内容变化时，实时更新右侧显示名称。"""
        self.error_lbl.setText("")
        self._update_display_name(text.strip())

    def _update_display_name(self, username: str):
        """查询显示名称并更新标签（走内存缓存，不读盘）。"""
        if not username:
            self.display_name_lbl.setText("")
            return
        if username in self._display_name_cache:
            self.display_name_lbl.setText(
                self._display_name_cache[username])
        else:
            self.display_name_lbl.setText("（账号不存在）")

    # ── 登录逻辑

    def _do_login(self):
        """点击登录按钮或回车时触发。"""
        username = self.username_input.text().strip()
        password = self.password_input.text()

        # 基本校验
        if not username:
            self._show_error("请输入账号名")
            self.username_input.setFocus()
            return
        if not password:
            self._show_error("请输入密码")
            self.password_input.setFocus()
            return

        # 加载账户配置
        try:
            accounts_data = load_accounts(self.myVault_path)
        except FileNotFoundError:
            self._show_error("找不到 accounts.conf，请先运行 vault_admin.py 创建账号")
            return
        except AccountsFormatError as e:
            self._show_error(f"accounts.conf 格式错误：{e}")
            return

        # 验证账号是否存在
        acc = get_account(accounts_data, username)
        if acc is None:
            self._show_error(f"账号「{username}」不存在")
            self.username_input.setFocus()
            return

        # 验证密码哈希
        if not verify_login(accounts_data, username, password):
            self._show_error("密码错误，请重试")
            self.password_input.clear()
            self.password_input.setFocus()
            return

        # 获取 vault 路径
        vault_path = get_vault_path(self.myVault_path, accounts_data, username)
        if not vault_path or not os.path.isfile(vault_path):
            self._show_error(
                f"找不到数据文件：{acc.get('vault_file', '')}\n"
                "请检查 MyVault/vaults/ 目录"
            )
            return

        # 加载 vault 文件（读取 kdf_params）
        try:
            vault_data = load_vault(vault_path)
        except (FileNotFoundError, VaultFormatError) as e:
            self._show_error(f"数据文件读取失败：{e}")
            return

        # 保存基本会话信息（密钥稍后派生）
        session.myVault_path = self.myVault_path
        session.current_account = username
        session.current_display_name = acc.get("display_name", username)
        session.vault_path = vault_path
        session.vault_data = vault_data   # 先存，密钥派生完后 session_key 才完整
        session.vault_content_hash = file_sha256(vault_path)  # 外部修改检测基准

        # 开始在后台派生密钥（迭代次数以 vault 文件 kdf_params 记录为准）
        kdf_params = vault_data.get("kdf_params", {})
        salt_b64 = kdf_params.get("salt", "")
        iterations = kdf_params.get("iterations", KDF_ITERATIONS)
        if not salt_b64:
            session.lock()
            self._show_error("数据文件缺少 kdf_params.salt，无法登录")
            return
        self._start_derive_key(password, salt_b64, iterations,
                               username, accounts_data)

    def _start_derive_key(self, password: str, salt_b64: str, iterations: int,
                          username: str, accounts_data: dict):
        """
        在 QThread 中派生密钥，期间显示进度条，禁用登录按钮。
        """
        self._set_loading(True)

        # 使用 QThread 运行派生工作
        self._derive_thread = QThread()
        self._derive_worker = DeriveKeyWorker(password, salt_b64, iterations)
        self._derive_worker.moveToThread(self._derive_thread)

        self._derive_thread.started.connect(self._derive_worker.run)
        self._derive_worker.finished.connect(
            lambda key: self._on_derive_finished(key, username, accounts_data)
        )
        self._derive_worker.error.connect(self._on_derive_error)
        self._derive_worker.finished.connect(self._derive_thread.quit)
        self._derive_worker.error.connect(self._derive_thread.quit)
        self._derive_thread.finished.connect(self._derive_thread.deleteLater)
        self._derive_thread.finished.connect(self._derive_worker.deleteLater)

        self._derive_thread.start()

    def _on_derive_finished(self, key: bytes, username: str, accounts_data: dict):
        """密钥派生成功，完成登录流程。"""
        self._set_loading(False)

        # 校验派生密钥确实能解密 vault：密码哈希只验证 accounts.conf，
        # 若账户配置与数据文件因云盘同步错位/冲突副本而不一致，
        # 会出现"登录成功但所有字段解密失败"，必须在此拦截
        first = (find_first_encrypted_field(session.vault_data)
                 if session.vault_data else None)
        if first is not None:
            entry_id, field_id, value = first
            try:
                decrypt_field(
                    value, key,
                    aad=field_aad(session.vault_data, entry_id, field_id))
            except (DecryptError, ValueError):
                session.lock()
                self._show_error(
                    "登录密码正确，但无法解密数据文件：\n"
                    "accounts.conf 与 vault 文件可能因云盘同步错位"
                    "或冲突副本而不匹配，数据文件也可能已损坏。\n"
                    "请检查 MyVault/vaults/ 目录后再重试。"
                )
                return

        # 将密钥存入 session
        session.session_key = key

        # version 1 旧格式升级到 version 2（AAD 绑定格式）：先弹确认框。
        # 默认按钮=升级；取消=放弃本次登录直接返回，数据文件零字节改动
        # （此时尚未调用 migrate，也未走到后面的 update_app_conf /
        # login_success.emit）。
        # 用户点「是」之后、migrate 之前：重算磁盘 SHA 与登录时记录的
        # vault_content_hash 比对——确认框可阻塞任意久，期间云盘可能
        # 改写文件；不一致则 session.lock() 并取消登录，绝不进入 migrate。
        # 确认且哈希一致后才执行迁移；任何失败（缺 ID、云盘同步竞态、
        # 磁盘错误）都重读磁盘，保证内存 version 与文件一致。
        # 升版未成功（upgrade_failures 非空）且重读到新数据时，必须用
        # 当前 session_key 对新 vault_data 的首个 ENC 字段再做一次
        # decrypt_field 复验——外部改动可能把不匹配的文件换进来；复验
        # 失败则 session.lock() 并取消登录（不再 emit login_success），
        # 复验成功才允许按 v1 继续。升版失败本身不阻断登录：界面明确
        # 提示 + 写一行崩溃日志，下次登录会再次确认并尝试；若重读也
        # 失败，旧的 vault_content_hash 会在下次保存时触发外部修改
        # 检测并强制锁屏，宁可锁屏也不写脏数据。
        if (session.vault_data and session.vault_path
                and session.vault_data.get("version", 1) == 1):
            reply = QMessageBox.question(
                self,
                "数据文件格式升级",
                "检测到当前数据文件为 version 1 旧格式。\n\n"
                "升级将把数据文件重写为 version 2（AAD 字段绑定）：\n"
                "· 升级前自动保留一份 .bak 备份（与原文件同目录）\n"
                "· 升级后旧版程序将无法打开该文件\n"
                "· 建议升级前在 MyVault/vaults/ 之外另存冷备份\n\n"
                "是否立即升级？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                # 取消：放弃登录。session.lock() 清除刚派生的密钥与
                # _do_login 预填的会话状态；数据文件尚未被触碰。
                session.lock()
                self.password_input.clear()
                self._show_error("已取消格式升级，本次登录已取消；数据文件未做任何修改。")
                return

            # 确认后、migrate 前：复核磁盘是否在确认期间被外部修改
            confirmed_hash = file_sha256(session.vault_path)
            if confirmed_hash != session.vault_content_hash:
                session.lock()
                self.password_input.clear()
                self._show_error(
                    "确认期间数据文件被外部修改，本次登录已取消，请重新登录")
                return

            upgrade_failures = []   # 界面用：异常类（步骤）
            upgrade_logs = []       # 日志用：含异常详情
            try:
                migrate_aad_format(session.vault_path, key, target_version=2)
            except Exception as e:
                upgrade_failures.append(f"{type(e).__name__}（升版迁移）")
                upgrade_logs.append(f"升版迁移 {type(e).__name__}: {e}")
            reread_ok = False
            try:
                session.vault_data = load_vault(session.vault_path)
                session.vault_content_hash = file_sha256(session.vault_path)
                reread_ok = True
            except Exception as e:
                upgrade_failures.append(f"{type(e).__name__}（升版后重读）")
                upgrade_logs.append(f"升版后重读 {type(e).__name__}: {e}")
            if upgrade_failures:
                # 升版未成功且拿到了重读数据：新数据可能与派生密钥不匹配
                #（确认期间被换成另一份文件），必须复验首个 ENC 字段
                if reread_ok:
                    first = (find_first_encrypted_field(session.vault_data)
                             if session.vault_data else None)
                    if first is not None:
                        entry_id, field_id, value = first
                        try:
                            decrypt_field(
                                value, key,
                                aad=field_aad(session.vault_data,
                                              entry_id, field_id))
                        except (DecryptError, ValueError):
                            session.lock()
                            self.password_input.clear()
                            self._show_error(
                                "升版失败后重读的数据文件无法用当前密钥解密"
                                "（确认期间可能被外部修改），本次登录已取消，"
                                "请重新登录")
                            return
                msg = ("数据文件格式升级未完成，仍处于 version 1，原因："
                       + "；".join(upgrade_failures))
                self._show_error(msg)
                try:
                    from main import _write_crash_log
                    _write_crash_log(f"[login] {msg} | "
                                     + "；".join(upgrade_logs))
                except Exception:
                    pass
                # 登录窗随即隐藏并销毁（deleteLater），延迟到主窗口
                # 打开后再弹明确提示；lambda 只捕获字符串、不引用 self，
                # 避免窗口已销毁后访问导致 RuntimeError
                QTimer.singleShot(800, lambda m=msg: QMessageBox.warning(
                    None, "数据文件格式升级", m
                    + "\n\n本次登录仍按 version 1 使用，下次登录会自动重试。"))

        # 检查云盘冲突文件
        conflicts = detect_conflict_files(session.vault_path)

        # 更新 app.conf：记录 last_account
        try:
            from accounts import update_app_conf
            update_app_conf(self.myVault_path, last_account=username)
        except Exception:
            pass

        # 清空密码框（安全）
        self.password_input.clear()

        # 发射登录成功信号（main.py 监听此信号开主窗口）
        self.login_success.emit()

        # 冲突提示延迟弹出（等主窗口打开后）
        if conflicts:
            QTimer.singleShot(800, lambda: self._show_conflict_warning(conflicts))

    def _on_derive_error(self, error_msg: str):
        """密钥派生失败（理论上不应发生，派生本身不会失败）。"""
        self._set_loading(False)
        session.lock()
        self._show_error(f"密钥派生失败：{error_msg}")

    def _show_conflict_warning(self, conflicts: list):
        """弹出云盘冲突文件提示。"""
        names = "\n".join(f"  · {c}" for c in conflicts)
        msg = QMessageBox(self)
        msg.setWindowTitle("检测到云盘冲突文件")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "检测到以下可能是云盘同步产生的冲突副本：\n\n"
            f"{names}\n\n"
            "建议您：\n"
            "1. 先备份当前 vaults/ 文件夹\n"
            "2. 手动比较两个文件的内容\n"
            "3. 确认无误后删除冲突副本"
        )
        open_btn = msg.addButton("打开文件夹", QMessageBox.ActionRole)
        msg.addButton("稍后处理", QMessageBox.RejectRole)
        msg.exec()

        if msg.clickedButton() == open_btn:
            vaults_dir = os.path.dirname(session.vault_path)
            self._open_folder(vaults_dir)

    def _open_folder(self, path: str):
        """用系统文件管理器打开指定文件夹。"""
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    # ── 辅助方法

    def _show_error(self, msg: str):
        """显示错误提示，4秒后自动清除。"""
        self.error_lbl.setText(msg)
        if hasattr(self, '_error_timer') and self._error_timer is not None:
            self._error_timer.stop()
            self._error_timer.deleteLater()
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(lambda: self.error_lbl.setText(""))
        self._error_timer.start(4000)

    def _set_loading(self, loading: bool):
        """切换加载状态：禁用输入控件，显示/隐藏进度条。"""
        self.login_btn.setEnabled(not loading)
        self.username_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
        self.progress_bar.setVisible(loading)
        if loading:
            self.login_btn.setText("验证中...")
            self.error_lbl.setText("")
        else:
            self.login_btn.setText("登 录")

    def keyPressEvent(self, event: QKeyEvent):
        """ESC 键清空密码框。"""
        if event.key() == Qt.Key_Escape:
            self.password_input.clear()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        """窗口关闭时确保 session 已清除并退出应用。"""
        session.lock()
        event.accept()
        QApplication.instance().quit()


# ─────────────────────────────────────────────
# 启动入口（供 main.py 调用）
# ─────────────────────────────────────────────

def get_app_dir() -> str:
    """返回程序所在目录的绝对路径。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_and_setup(app_dir: str) -> str | None:
    """
    检查是否已配置 MyVault 路径。
    - 已配置且有效：直接返回路径
    - 未配置或无效：显示引导窗口，引导完成后返回路径
    - 用户关闭引导窗口：返回 None（程序退出）

    参数：
        app_dir - VaultApp 程序目录
    返回：
        有效的 myVault_path 字符串，或 None
    """
    path = read_app_config(app_dir)

    if path and os.path.isdir(path) and os.path.isfile(get_accounts_path(path)):
        return path

    # 需要引导：用 QEventLoop 阻塞等待引导窗口关闭
    # （替代 while + processEvents 的忙轮询，行为一致但不空耗 CPU）
    result = [None]
    loop = QEventLoop()

    def _on_setup_done(p: str):
        result[0] = p
        loop.quit()

    wizard = SetupWizard(app_dir)
    wizard.setup_done.connect(_on_setup_done)
    wizard.closed.connect(loop.quit)
    wizard.show()

    loop.exec()

    return result[0]


# ─────────────────────────────────────────────
# 独立运行预览（python ui/login.py）
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
# 图标辅助函数
# ─────────────────────────────────────────────

def _set_window_icon(window):
    """为窗口设置应用图标（ICO 优先，回退 PNG）。"""
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(app_dir, "assets", "icon.ico")
    png_path = os.path.join(app_dir, "assets", "icon.png")
    from PySide6.QtGui import QIcon
    if os.path.isfile(ico_path):
        window.setWindowIcon(QIcon(ico_path))
    elif os.path.isfile(png_path):
        window.setWindowIcon(QIcon(png_path))


if __name__ == "__main__":
    import tempfile

    app = QApplication(sys.argv)

    # 应用深色主题
    from styles import apply_theme
    apply_theme(app, "dark")

    # 创建临时测试环境
    tmpdir = tempfile.mkdtemp()
    vaults_dir = os.path.join(tmpdir, "vaults")
    os.makedirs(vaults_dir)

    # 创建测试账号
    from accounts import create_account
    from vault_io import create_empty_vault
    create_account(tmpdir, "main", "大号", "test123", "export456")
    vault_path = os.path.join(tmpdir, "vaults", "main.vault")
    create_empty_vault(vault_path, "main")

    print(f"测试环境：{tmpdir}")
    print("测试账号：main / 密码：test123")

    win = LoginWindow(tmpdir)

    def on_login():
        print(f"✓ 登录成功！")
        print(f"  账号：{session.current_account}（{session.current_display_name}）")
        print(f"  Vault 条目数：{len(session.vault_data.get('entries', []))}")
        QMessageBox.information(win, "登录成功",
            f"账号：{session.current_account}\n"
            f"显示名：{session.current_display_name}\n"
            "（主窗口将在这里打开）")
        app.quit()

    win.login_success.connect(on_login)
    win.show()

    # 同时测试引导窗口
    print("\n提示：关闭登录窗口后会显示引导窗口预览")

    sys.exit(app.exec())
