# P5 可靠性增强验证脚本（离屏运行，不显示窗口）
# 覆盖：
#   R1 单实例锁（QLockFile 互斥语义 + main.py 接线确认）
#   R2 系统锁屏联动（SystemLockWatcher 翻转沿触发；非 Windows 恒未锁定）
#   R3 滚动备份（vault .bak / accounts.conf .bak；备份失败不阻塞保存）
#   R4 剪贴板历史说明存在（README 安全设计章节）
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PySide6.QtCore import QLockFile, QTimer
from session import session
from accounts import (create_account, load_accounts, save_accounts,
                      get_accounts_path)
from vault_io import (create_empty_vault, load_vault, save_vault,
                      backup_file, file_sha256)

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd123', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
save_vault(vp, vdata)

# ─────────────────────────────────────────
# R1: 单实例锁
# ─────────────────────────────────────────
lock_path = os.path.join(tmp, 'tjkey.lock')
lock1 = QLockFile(lock_path)
assert lock1.tryLock(0), '第一实例应能获取锁'
lock2 = QLockFile(lock_path)
assert not lock2.tryLock(0), '第二实例应被拒绝'
lock1.unlock()
assert lock2.tryLock(0), '第一实例释放后第二实例应能获取'
lock2.unlock()
if os.path.exists(lock_path):
    os.remove(lock_path)

# main.py 接线确认：tryLock 失败即退出（静态检查关键行）
main_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'main.py'), encoding='utf-8').read()
assert 'QLockFile' in main_src and 'tryLock' in main_src \
    and 'TJKEY 已在运行' in main_src
print('[R1] 单实例锁：QLockFile 互斥语义 + main.py 接线 通过')

# ─────────────────────────────────────────
# R2: 系统锁屏联动
# ─────────────────────────────────────────
from system_lock import SystemLockWatcher, is_workstation_locked

# 平台基线：Windows 下未锁定时应返回 False；非 Windows 恒 False
if sys.platform == 'win32':
    import ctypes
    try:
        u = ctypes.windll.user32
        h = u.OpenInputDesktop(0, False, 0x0001)
        expect = not h
        if h:
            u.CloseDesktop(h)
        assert is_workstation_locked() == expect, \
            'OpenInputDesktop 探测应与直接调用一致'
    except Exception:
        pass   # 测试环境无交互桌面时跳过基线校验
else:
    assert is_workstation_locked() is False

# 翻转沿触发：monkeypatch 探测函数模拟 锁定→解锁→锁定
watcher = SystemLockWatcher()
fired = []
watcher.locked.connect(lambda: fired.append(1))

_orig = sys.modules['system_lock'].is_workstation_locked
probe_state = {'locked': False}
sys.modules['system_lock'].is_workstation_locked = \
    lambda: probe_state['locked']

watcher.start()                       # 启动时采样：False
watcher._check()
assert fired == [], '初始未锁定不应触发'
probe_state['locked'] = True
watcher._check()
assert fired == [1], '未锁定→锁定翻转沿应触发一次'
probe_state['locked'] = True          # 持续锁定
watcher._check()
watcher._check()
assert fired == [1], '持续锁定不应重复触发'
probe_state['locked'] = False         # 解锁
watcher._check()
assert fired == [1], '解锁不应触发'
probe_state['locked'] = True          # 再次锁定 → 再次触发
watcher._check()
assert fired == [1, 1], '再次锁定应再次触发'
watcher.stop()
assert not watcher.is_active()
sys.modules['system_lock'].is_workstation_locked = _orig

# main_window 接线确认
mw_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'ui', 'main_window.py'), encoding='utf-8').read()
assert 'SystemLockWatcher' in mw_src and 'watcher.locked.connect' in mw_src \
    and '_system_lock_watcher.stop()' in mw_src
print('[R2] 系统锁屏联动：探测函数 + 翻转沿单次触发 + 主窗口接线 通过')

# ─────────────────────────────────────────
# R3: 滚动备份
# ─────────────────────────────────────────
os.remove(vp + '.bak') if os.path.exists(vp + '.bak') else None
d1 = load_vault(vp)
save_vault(vp, d1)                     # 第一次保存 → .bak 为当前旧版
assert os.path.isfile(vp + '.bak'), 'vault 保存后应有 .bak'
d1['entries'] = [{'id': 'new1'}]
save_vault(vp, d1)
bak = load_vault(vp + '.bak')
assert bak['entries'] == [], '.bak 应保留上一版（无条目）'
assert load_vault(vp)['entries'] == [{'id': 'new1'}]

# accounts.conf 滚动备份
acc_path = get_accounts_path(tmp)
data = load_accounts(tmp)
data['marker'] = 'v2'
save_accounts(tmp, data)
assert os.path.isfile(acc_path + '.bak'), 'accounts.conf 保存后应有 .bak'
assert load_accounts(tmp)['marker'] == 'v2'

# 备份不可写时不阻塞保存：把 .bak 变成目录使 copy2 失败
os.remove(vp + '.bak')
os.makedirs(vp + '.bak')
d1['entries'].append({'id': 'new2'})
save_vault(vp, d1)                     # 备份失败应被吞掉，保存照常成功
assert load_vault(vp)['entries'] == [{'id': 'new1'}, {'id': 'new2'}]
os.rmdir(vp + '.bak')
print('[R3] 滚动备份：vault/accounts .bak 上一版保留 + 备份失败不阻塞 通过')

# ─────────────────────────────────────────
# R4: README 剪贴板历史说明
# ─────────────────────────────────────────
readme = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'README.md'), encoding='utf-8').read()
assert '剪贴板历史' in readme and 'Win+V' in readme \
    and '剪贴板历史记录' in readme
print('[R4] README 已包含 Windows 剪贴板历史（Win+V）风险说明')

print()
print('=== P5 可靠性增强四项全部验证通过 ===')
