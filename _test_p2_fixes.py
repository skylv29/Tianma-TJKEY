# P2 修复验证脚本（离屏运行，不显示窗口）
# 覆盖：
#   P2-1 derive_key 按 vault 记录的迭代次数派生（主程序与 recover.py 一致）
#   P2-2 URL 打开仅放行 http/https
#   P2-3 保存前外部修改检测（防止旧内存快照覆盖 vault_admin 改密后的文件）
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from session import session
from accounts import create_account
from vault_io import (create_empty_vault, load_vault, save_vault,
                      save_vault_checked, file_sha256,
                      VaultExternallyModifiedError)
from crypto import derive_key, encrypt_field, decrypt_field, DecryptError, build_field_aad

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
key = derive_key('RightPwd', vdata['kdf_params']['salt'])
vdata['entries'].append({
    'id': 'e1', 'name': '测试条目', 'category_id': None, 'subcategory_id': None,
    'order': 0, 'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
    'fields': [
        {'id': 'fld_001', 'label': '密码', 'type': 'secret',
         'value': encrypt_field('real_secret', key,
                                aad=build_field_aad('e1', 'fld_001')), 'order': 0},
    ],
})
save_vault(vp, vdata)

# ─────────────────────────────────────────
# P2-1: derive_key 按 vault 记录的迭代次数派生；非法值拒绝
# ─────────────────────────────────────────
loaded = load_vault(vp)
salt = loaded['kdf_params']['salt']
loaded['kdf_params']['iterations'] = 10000    # 模拟非默认迭代次数的 vault
save_vault(vp, loaded)

low_iter_key = derive_key('RightPwd', salt, 10000)
enc = encrypt_field('iter_secret', low_iter_key, aad=None)
assert decrypt_field(enc, low_iter_key, aad=None) == 'iter_secret'
try:
    decrypt_field(enc, derive_key('RightPwd', salt), aad=None)   # 默认 600000 轮
    raise AssertionError('迭代次数不同的密钥不应解密成功')
except DecryptError:
    pass
print('[P2-1] 迭代次数实际参与密钥派生（非默认次数的 vault 可正确登录）')

for bad in (0, -5, 10**12, 'x', None, True):
    try:
        derive_key('p', salt, bad)
        raise AssertionError(f'非法迭代次数应抛 ValueError: {bad!r}')
    except ValueError:
        pass
print('[P2-1] 非法迭代次数（0/负数/超上限/非整数/bool）被拒绝')

# ─────────────────────────────────────────
# P2-3: 保存前外部修改检测（vault_io 层）
# ─────────────────────────────────────────
loaded = load_vault(vp)
h1 = file_sha256(vp)

loaded['entries'][0]['name'] = '改名后'
h2 = save_vault_checked(vp, loaded, known_hash=h1)
assert h2 and h2 != h1 and file_sha256(vp) == h2
print('[P2-3] 无外部修改时正常保存，并返回新的哈希基准')

# 模拟外部程序（vault_admin 改密 / 云盘同步）改写磁盘文件
ext = load_vault(vp)
ext['external_marker'] = 1
save_vault(vp, ext)
assert file_sha256(vp) != h2

try:
    save_vault_checked(vp, loaded, known_hash=h2)   # 内存旧快照 + 旧基准
    raise AssertionError('外部修改后应拒绝保存')
except VaultExternallyModifiedError:
    pass
assert load_vault(vp).get('external_marker') == 1, '磁盘内容不应被旧快照覆盖'
print('[P2-3] 外部修改后旧内存快照的保存被拒绝，磁盘内容未被覆盖')

# ─────────────────────────────────────────
# P2-3b: UI 链路 save_vault_or_lock —— 检测到外部修改后强制锁屏
# ─────────────────────────────────────────
import ui.vault_sync as vs
vs.QMessageBox.warning = staticmethod(lambda *a, **k: None)   # 屏蔽弹窗

session.myVault_path = tmp
session.vault_path = vp
session.vault_data = loaded            # 内存中仍是旧快照
session.session_key = key
session.current_account = 'main'
session.current_display_name = '大号'
session.vault_content_hash = h2        # 基准仍是旧哈希（磁盘已被外部改写）

assert vs.save_vault_or_lock() is False
assert session.is_locked() and session.vault_data is None
print('[P2-3] save_vault_or_lock：外部修改 → 拒绝保存并强制锁屏回登录')

# 重新登录（加载磁盘最新数据）后可正常保存
loaded2 = load_vault(vp)
session.session_key = key
session.vault_data = loaded2
session.vault_path = vp
session.vault_content_hash = file_sha256(vp)
assert vs.save_vault_or_lock() is True
assert session.vault_content_hash == file_sha256(vp)
print('[P2-3] 重新加载最新数据后保存成功，哈希基准已更新')

# ─────────────────────────────────────────
# P2-2: URL 打开仅放行 http/https
# ─────────────────────────────────────────
import webbrowser
import ui.entry_detail as ed
ed.QMessageBox.warning = staticmethod(lambda *a, **k: None)

opened = []
webbrowser.open = lambda u: opened.append(u) or True

panel = ed.EntryDetailPanel()
panel.url_lbl.setText('https://good.example.com')
panel._open_url()
panel.url_lbl.setText('http://good2.example.com')
panel._open_url()
panel.url_lbl.setText('www.plain.example.com')     # 无协议 → 自动补 https
panel._open_url()
assert opened == ['https://good.example.com',
                  'http://good2.example.com',
                  'https://www.plain.example.com'], opened

panel.url_lbl.setText('file:///C:/Windows/system.ini')
panel._open_url()
panel.url_lbl.setText('ftp://evil.example.com/x')
panel._open_url()
panel.url_lbl.setText('javascript:alert(1)')
panel._open_url()
assert len(opened) == 3, f'非 http/https 协议应全部被拦截: {opened}'
print('[P2-2] URL 打开：http/https 放行，无协议自动补 https，其余协议拦截')

print()
print('=== P2 三项修复全部验证通过 ===')
