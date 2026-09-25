# system_lock.py
# 系统锁屏状态检测（Windows）
#
# 用于"系统锁屏联动"：Windows 会话被锁定（Win+L / Ctrl+Alt+Del）时
# 立即触发应用自动锁屏，而不是等到应用自身的无操作超时——
# 离开电脑锁了系统，密码管理器不应保持解锁状态。
#
# 实现说明：
#   通过 OpenInputDesktop 探测当前是否存在可交互输入桌面——
#   会话锁定时系统切换到 Winlogon 桌面，OpenInputDesktop 返回 NULL。
#   轮询间隔 3 秒，单次系统调用的开销可忽略。
#   非 Windows 平台恒返回 False（联动不生效，其余功能不受影响）。

import sys

from PySide6.QtCore import QObject, QTimer, Signal

DESKTOP_READOBJECTS = 0x0001


def is_workstation_locked() -> bool:
    """返回当前 Windows 会话是否处于锁定状态；非 Windows 平台恒为 False。"""
    if sys.platform != "win32":
        return False
    import ctypes
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if hdesk:
            user32.CloseDesktop(hdesk)
            return False
        return True
    except Exception:
        # 探测失败（权限/接口异常）按"未锁定"处理，不影响正常使用
        return False


class SystemLockWatcher(QObject):
    """
    周期探测系统锁屏状态，状态从未锁定翻转为锁定时发射 locked 信号。

    主窗口连接该信号调用 _do_lock()（内置已锁屏守卫，重复触发无副作用）。
    只在翻转沿发射一次，系统解锁后再次锁定会再次触发。
    """

    locked = Signal()

    POLL_INTERVAL_MS = 3000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._was_locked = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._check)

    def start(self):
        """启动探测（先同步采样一次，避免把启动时的锁定状态误报为翻转）。"""
        self._was_locked = is_workstation_locked()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def is_active(self) -> bool:
        return self._timer.isActive()

    def _check(self):
        locked = is_workstation_locked()
        if locked and not self._was_locked:
            self.locked.emit()
        self._was_locked = locked
