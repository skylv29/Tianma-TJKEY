# P1 修复验证脚本（离屏运行，不显示窗口）
# 覆盖：
#   P1-1 编辑面板解密失败清空字段 + 保存拦截 ENC: 密文（防二次加密）
#   P1-2 锁屏/重新登录清理详情、编辑面板与列表选中状态
#   P1-3 登录时校验派生密钥能否解密 vault
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from session import session
from accounts import create_account
from vault_io import create_empty_vault, load_vault, save_vault
from crypto import derive_key, encrypt_field, decrypt_field, DecryptError, build_field_aad

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
key = derive_key('RightPwd', vdata['kdf_params']['salt'])
wrong_key = derive_key('OtherPwd', vdata['kdf_params']['salt'])

# 一好一坏两个 secret 字段：坏字段用其他密钥加密，模拟解密失败
vdata['entries'].append({
    'id': 'e1', 'name': '测试条目', 'category_id': None, 'subcategory_id': None,
    'order': 0, 'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
    'fields': [
        {'id': 'fld_001', 'label': '密码', 'type': 'secret',
         'value': encrypt_field('real_secret', key,
                                aad=build_field_aad('e1', 'fld_001')), 'order': 0},
        {'id': 'fld_002', 'label': '坏字段', 'type': 'secret',
         'value': encrypt_field('lost_data', wrong_key,
                                aad=build_field_aad('e1', 'fld_002')), 'order': 1},
    ],
})
# 记录坏字段原始密文，供保存后断言"解密失败字段防被空值覆盖"使用
orig_bad_cipher = vdata['entries'][0]['fields'][1]['value']
save_vault(vp, vdata)

# 屏蔽弹窗（离屏环境下 QMessageBox 会阻塞）
import ui.entry_edit as ee
ee.QMessageBox.warning = staticmethod(lambda *a, **k: None)

session.myVault_path = tmp
session.vault_path = vp
session.vault_data = load_vault(vp)
session.session_key = key
session.current_account = 'main'
session.current_display_name = '大号'

# ─────────────────────────────────────────
# P1-1: 编辑面板解密失败清空显示 + 保存时保留原密文（防被空值覆盖）+ 无二次加密
# ─────────────────────────────────────────
from ui.entry_edit import EntryEditPanel
panel = EntryEditPanel()
panel.load_edit_entry('e1')
rows = panel._field_rows
assert rows[0].get_value() == 'real_secret', f'好字段应解密: {rows[0].get_value()!r}'
assert rows[1].get_value() == '', f'坏字段 UI 应显示为空: {rows[1].get_value()!r}'
print('[P1-1] 解密失败字段 UI 已清空（不再保留 ENC: 密文）')

panel.name_input.setText('测试条目')
panel._do_save()
saved = load_vault(vp)
f0, f1 = saved['entries'][0]['fields']
assert decrypt_field(f0['value'], key, aad=build_field_aad('e1', 'fld_001')) == 'real_secret'
# 修复"解密失败字段防被空值覆盖"后：UI 显示为空，但保存必须回写原密文，
# 否则用户未触碰的坏字段会被编辑面板的空值覆盖导致数据丢失
assert f1['value'] == orig_bad_cipher, f'坏字段保存后应保留原密文: {f1["value"]!r}'
print('[P1-1] 保存后无二次加密：好字段可解密，坏字段保留原密文')

# 保存拦截：secret 输入 ENC: 开头的值应拒绝保存且不写盘
before = open(vp, 'rb').read()
panel2 = EntryEditPanel()
panel2.load_edit_entry('e1')
panel2._field_rows[0]._value_widget.input.setText('ENC:fake_ciphertext')
panel2.name_input.setText('测试条目')
panel2._do_save()
assert open(vp, 'rb').read() == before, '文件不应被修改'
print('[P1-1] 保存拦截 ENC: 密文输入（文件未被修改）')

# ─────────────────────────────────────────
# P1-2: 锁屏与重新登录清理面板
# ─────────────────────────────────────────
from ui.main_window import MainWindow
win = MainWindow()
win.on_login()

win.detail_panel.load_entry('e1')
win.list_panel.select_entry('e1')
win.edit_panel.load_edit_entry('e1')       # 编辑面板此时持有解密后的明文
win.right_stack.setCurrentIndex(1)         # 模拟用户正在编辑时锁屏
assert win.detail_panel._current_entry_id == 'e1'

locked = []
win.lock_requested.connect(lambda: locked.append(1))
win._do_lock()
assert locked, 'lock_requested 应发射'
assert session.is_locked(), 'session 应被清空'
assert win.detail_panel._current_entry_id is None
assert win.detail_panel.fields_layout.count() == 1, '详情字段行应被销毁（只剩 stretch）'
assert win.edit_panel._field_rows == [], '编辑面板字段行应被销毁'
assert win.list_panel._current_entry_id is None
print('[P1-2] 锁屏清理：明文控件销毁、选中状态清除')

# 重新登录（换账号/再登录同路径）
session.session_key = key
session.vault_data = load_vault(vp)
session.vault_path = vp
session.current_account = 'main'
session.current_display_name = '大号'
win.on_login()
assert win.right_stack.currentIndex() == 0, '重新登录应回到查看模式'
assert win.detail_panel._current_entry_id is None
assert win.detail_panel.fields_layout.count() == 1
assert win.edit_panel._field_rows == []
print('[P1-2] 重新登录后界面无残留，回到查看模式')

# ─────────────────────────────────────────
# P1-3: 登录时校验派生密钥
# ─────────────────────────────────────────
from ui.login import LoginWindow
login_win = LoginWindow(tmp)
emitted = []
login_win.login_success.connect(lambda: emitted.append(1))

# 模拟 _do_login 已完成的会话预填
session.myVault_path = tmp
session.current_account = 'main'
session.current_display_name = '大号'
session.vault_path = vp
session.vault_data = load_vault(vp)

# 密钥不匹配（哈希验证能过、但 vault 是另一密码加密的错位场景）
login_win._on_derive_finished(
    derive_key('MismatchPwd', session.vault_data['kdf_params']['salt']), 'main', {})
assert not emitted, '密钥不匹配时不应发射 login_success'
assert session.is_locked(), '失败后 session 应被清空'
print('[P1-3] 密钥与数据不匹配 → 拦截登录并清空会话')

# 正确密钥（模拟用户重试：真实流程会重新走 _do_login 填回会话状态）
session.vault_data = load_vault(vp)
login_win._on_derive_finished(key, 'main', {})
assert emitted and session.session_key == key
print('[P1-3] 密钥匹配 → 正常登录')

# 无加密字段的 vault 应直接通过（无可校验对象）
vp2 = os.path.join(tmp, 'vaults', 'empty.vault')
session.vault_data = create_empty_vault(vp2, 'main')
session.vault_path = vp2
emitted.clear()
login_win2 = LoginWindow(tmp)
login_win2.login_success.connect(lambda: emitted.append(1))
session.current_account = 'main'
login_win2._on_derive_finished(key, 'main', {})
assert emitted and session.session_key == key
print('[P1-3] 无加密字段的 vault 正常登录')

# ─────────────────────────────────────────
# P1-4: 锁屏计时器守卫——登录界面显示期间（session 已锁）交互
#       不应重启计时器；计时器意外到期也不应再次发射 lock_requested
# ─────────────────────────────────────────
# 重新登录，恢复未锁定状态
session.session_key = key
session.vault_data = load_vault(vp)
session.vault_path = vp
session.current_account = 'main'
session.current_display_name = '大号'

from ui.main_window import MainWindow
win = MainWindow()
win.on_login()
assert win._lock_timer.isActive(), '登录后自动锁屏计时器应处于运行状态'

fired = []
win.lock_requested.connect(lambda: fired.append(1))
win._do_lock()                       # 正常锁屏路径
assert fired and session.is_locked()
assert not win._lock_timer.isActive()

# 模拟登录界面上的用户交互（全局事件过滤器会调用 _reset_lock_timer）
win._reset_lock_timer()
assert not win._lock_timer.isActive(), '锁屏状态下不应重启自动锁屏计时器'

# 计时器若在登录界面意外到期，不应再次锁屏（否则会叠加新的登录窗口）
fired.clear()
win._do_lock()
assert not fired, '已锁屏时 _do_lock 不应再次发射 lock_requested'
print('[P1-4] 锁屏计时器守卫：登录界面不重启计时器、不重复触发锁屏')

print()
print('=== P1 四项修复全部验证通过 ===')
