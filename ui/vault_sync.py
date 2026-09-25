# ui/vault_sync.py
# UI 层统一的 vault 保存入口
#
# 所有面板保存 vault 都应使用 save_vault_or_lock()，而不是直接调用
# vault_io.save_vault：
#   - 保存前校验文件内容未被外部程序修改（云盘同步、vault_admin 等）
#   - 检测到外部修改时弹窗提示并强制锁屏回登录界面。
#     背景：主程序把整个 vault 快照放在内存里，若 vault_admin 在主程序
#     运行期间用新密码重加密了文件，主程序的下一次保存会用旧密钥的
#     密文整体覆盖磁盘，之后所有加密字段都无法解密（数据损坏）。
#     强制回登录可丢弃过期的内存快照，重新加载磁盘上的最新数据。

from PySide6.QtWidgets import QMessageBox

from session import session
from vault_io import save_vault_checked, VaultExternallyModifiedError


def save_vault_or_lock() -> bool:
    """
    保存 session.vault_data 到 session.vault_path（带外部修改检测）。

    返回：
        True  - 保存成功
        False - 保存失败：文件被外部修改（已强制锁屏回登录界面）或
                写入出错（磁盘满等）。两种失败均已弹窗提示，调用方
                只需根据返回值决定是否继续后续 UI 操作。
    """
    try:
        session.vault_content_hash = save_vault_checked(
            session.vault_path, session.vault_data, session.vault_content_hash)
        return True
    except VaultExternallyModifiedError:
        QMessageBox.warning(
            None, "保存已取消",
            "数据文件已被其他程序修改（可能是云盘同步或 vault_admin 工具）。\n\n"
            "为防止用内存中的旧数据覆盖外部修改、导致数据无法解密，"
            "本次保存已取消，程序将返回登录界面。\n"
            "重新登录后将加载磁盘上的最新数据。")
        _force_lock()
        return False
    except IOError as e:
        QMessageBox.warning(None, "保存失败", f"数据保存失败：{e}")
        return False


def _force_lock():
    """外部修改后强制锁屏：清空面板明文与内存快照，回到登录界面。"""
    main_window = session.main_window
    if main_window is not None:
        # 走标准锁屏流程：清理面板明文 → session.lock() → 发射 lock_requested
        main_window._do_lock()
    else:
        session.lock()
