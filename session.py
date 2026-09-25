# session.py
# TJKEY 全局运行时状态
# 本文件管理登录后的内存状态，包括加密密钥和当前 vault 数据
# session_key 只存在于内存中，锁屏或退出时必须清除

import os


class Session:
    """
    全局单例，保存当前登录会话的所有运行时状态。
    程序中通过 from session import session 访问唯一实例。
    """

    def __init__(self):
        # MyVault 数据文件夹的绝对路径（从 app.config 读取）
        self.myVault_path: str = ""

        # 当前登录的账号 username（如 "main"、"sub1"）
        self.current_account: str = ""

        # 当前登录账号的显示名称（如 "大号"、"小号1"）
        self.current_display_name: str = ""

        # 由登录密码派生的 AES-256 密钥（32字节）
        # 此值永远不写入任何文件，锁屏/退出时必须设为 None
        self.session_key: bytes | None = None

        # 当前 vault 文件的完整解析内容（Python dict）
        # 条目、分类、模板都在这里
        self.vault_data: dict | None = None

        # 当前 vault 文件的绝对路径（保存时使用）
        self.vault_path: str = ""

        # 当前 vault 文件内容的 SHA-256（登录加载和每次成功保存后更新）。
        # 保存前用它检测文件是否被外部程序修改（云盘同步 / vault_admin）
        self.vault_content_hash: str | None = None

        # 主窗口引用（用于自动锁屏计时器触发 UI 切换）
        self.main_window = None

        # 本程序最近一次写入剪贴板的值（复制密码后由 entry_detail 登记）。
        # 锁屏/退出时据此匹配清空，防止密码在 30 秒清空定时器触发前
        # 随进程退出永久残留于系统剪贴板。
        self.last_clipboard_text: str | None = None

    def lock(self):
        """
        锁屏：清除密钥和敏感数据，但保留路径配置。
        调用时机：自动锁屏计时器触发、手动点击锁屏按钮、退出程序。
        """
        self.session_key = None
        self.vault_data = None
        self.current_account = ""
        self.current_display_name = ""
        self.vault_path = ""
        self.vault_content_hash = None
        self.last_clipboard_text = None

    def clear_clipboard_if_ours(self) -> None:
        """若剪贴板内容仍是本程序复制的值，则清空（锁屏/退出时调用）。"""
        expected = self.last_clipboard_text
        if not expected:
            return
        try:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            if clipboard is not None and clipboard.text() == expected:
                clipboard.clear()
        except Exception:
            pass
        self.last_clipboard_text = None

    def is_locked(self) -> bool:
        """返回当前是否处于锁屏状态（密钥不存在即为锁定）。"""
        return self.session_key is None

    def is_configured(self) -> bool:
        """返回是否已配置 MyVault 路径（用于判断是否需要首次引导）。"""
        return bool(self.myVault_path) and os.path.isdir(self.myVault_path)


# 全局唯一实例，所有模块 import 这一个对象
session = Session()
