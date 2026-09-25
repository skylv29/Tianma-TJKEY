# P4 功能补全验证脚本（离屏运行，不显示窗口）
# 覆盖四个新功能：
#   F1 密码生成器（crypto.generate_password + 编辑面板生成按钮/对话框）
#   F2 应用内修改登录密码（设置入口 + ChangePasswordDialog + 强制锁屏）
#   F3 首次引导建号（SetupWizard + _CreateAccountDialog）
#   F4 软删除回收站（软删/恢复/永久删除 + 列表/搜索/到期/导出全口径过滤）
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from session import session
from accounts import (create_account, load_accounts, verify_login,
                      get_vault_path, DEFAULT_APP_CONF)
from vault_io import (create_empty_vault, load_vault, save_vault,
                      add_category, add_subcategory, delete_entry,
                      restore_entry, purge_entry, get_deleted_entries,
                      get_entries_by_category, search_entries, scan_expiry,
                      count_active_entries, file_sha256)
from crypto import derive_key, encrypt_field, decrypt_field, generate_password, build_field_aad

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd123', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
key = derive_key('RightPwd123', vdata['kdf_params']['salt'])
cat = add_category(vdata, '域名注册')
vdata['entries'].append({
    'id': 'e1', 'name': 'Cloudflare 主号', 'category_id': cat['id'],
    'subcategory_id': None, 'order': 0,
    'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
    'fields': [
        {'id': 'fld_001', 'label': '用户名', 'type': 'text',
         'value': 'admin@example.com', 'order': 0},
        {'id': 'fld_002', 'label': '密码', 'type': 'secret',
         'value': encrypt_field('real_secret', key,
                                aad=build_field_aad('e1', 'fld_002')), 'order': 1},
        {'id': 'fld_003', 'label': '域名', 'type': 'date_domain',
         'value': 'example.com|2026-12-31', 'order': 2},
    ],
})
save_vault(vp, vdata)

session.myVault_path = tmp
session.vault_path = vp
session.vault_data = load_vault(vp)
session.session_key = key
session.current_account = 'main'
session.current_display_name = '大号'
session.vault_content_hash = file_sha256(vp)

# ─────────────────────────────────────────
# F1: 密码生成器
# ─────────────────────────────────────────
for _ in range(100):
    p = generate_password(16)
    assert len(p) == 16
    assert any(c.islower() for c in p) and any(c.isupper() for c in p) \
        and any(c.isdigit() for c in p) and any(c in '!@#$%^&*-_=+?' for c in p), p
    assert not any(c in '0Oo1lI' for c in p), f'易混淆字符泄漏: {p}'
p_plain = generate_password(12, upper=False, digits=False, symbols=False)
assert p_plain.islower() and p_plain.isalpha()
try:
    generate_password(4); raise AssertionError('应拒绝超短长度')
except ValueError:
    pass

from ui.entry_edit import _SecretInput, _PasswordGeneratorDialog
w = _SecretInput('')
dlg = _PasswordGeneratorDialog()
w.input.setText(dlg.get_password())
assert w.get_value(), '生成按钮回填后应有值'
dlg.chk_symbols.setChecked(False)
assert not any(c in '!@#$%^&*-_=+?' for c in dlg.get_password())
print('[F1] 密码生成器：100 轮字符类/易混淆断言 + UI 回填联动 通过')

# ─────────────────────────────────────────
# F2: 应用内修改登录密码
# ─────────────────────────────────────────
import ui.change_password_dialog as cpd
cpd.QMessageBox.information = staticmethod(lambda *a, **k: None)
cpd.QMessageBox.warning = staticmethod(lambda *a, **k: None)
from ui.change_password_dialog import ChangePasswordDialog

dlg = ChangePasswordDialog()
# 错误分支不改数据
dlg.old_input.setText('Old'); dlg.new_input.setText('NewPwd12345')
dlg.confirm_input.setText('NewPwd12345')
dlg._do_change()
assert verify_login(load_accounts(tmp), 'main', 'RightPwd123')
# 正常改密 → vault 重加密 + 强制锁屏
locked = []
class FakeMW:
    def _do_lock(self):
        locked.append(1)
        session.lock()
session.main_window = FakeMW()
dlg.old_input.setText('RightPwd123')
dlg.new_input.setText('NewPwd12345'); dlg.confirm_input.setText('NewPwd12345')
dlg._do_change()
assert verify_login(load_accounts(tmp), 'main', 'NewPwd12345')
assert not verify_login(load_accounts(tmp), 'main', 'RightPwd123')
assert locked == [1] and session.is_locked()

# 重新登录后新密钥可解密（软删除条目也会被重加密处理）
vd = load_vault(vp)
k2 = derive_key('NewPwd12345', vd['kdf_params']['salt'])
assert decrypt_field(vd['entries'][0]['fields'][1]['value'], k2,
                     aad=build_field_aad('e1', 'fld_002')) == 'real_secret'

# 恢复会话供后续测试
session.session_key = k2
session.vault_data = vd
session.vault_path = vp
session.vault_content_hash = file_sha256(vp)
print('[F2] 应用内改密：错误分支不改动、正常改密重加密+锁屏 通过')

# ─────────────────────────────────────────
# F3: 首次引导建号
# ─────────────────────────────────────────
from ui.login import SetupWizard, _CreateAccountDialog
fresh = tempfile.mkdtemp()

wiz = SetupWizard(fresh)
wiz.selected_path = fresh
wiz._validate_path(fresh)
assert wiz.create_btn.isVisibleTo(wiz), '空文件夹应显示建号按钮'
assert not wiz.confirm_btn.isEnabled()

dlg_a = _CreateAccountDialog(fresh)
dlg_a.username_input.setText('alice')
dlg_a.display_input.setText('爱丽丝')
dlg_a.pwd_input.setText('AlicePwd123'); dlg_a.pwd2_input.setText('AlicePwd123')
dlg_a.exp_input.setText('AliceExp1234'); dlg_a.exp2_input.setText('AliceExp1234')
dlg_a._do_create()
assert dlg_a.created_username == 'alice'
assert verify_login(load_accounts(fresh), 'alice', 'AlicePwd123')
assert os.path.isfile(get_vault_path(fresh, load_accounts(fresh), 'alice'))
assert os.path.isfile(os.path.join(fresh, 'README.txt'))

# 创建后向导自动启用"确认并开始使用"
wiz._validate_path(fresh)
assert wiz.confirm_btn.isEnabled() and not wiz.create_btn.isVisibleTo(wiz)

# 错误分支：重复用户名 / 非法字符 / 密码过短 / 两次不一致
for un, p1, p2, ep1, ep2, expect_ok in [
    ('alice', 'BobPwd12345', 'BobPwd12345', 'BobExp123456', 'BobExp123456', False),  # 重复
    ('bad name', 'BobPwd12345', 'BobPwd12345', 'BobExp123456', 'BobExp123456', False),  # 非法
    ('bob', 'short', 'short', 'BobExp123456', 'BobExp123456', False),                # 过短
    ('bob', 'BobPwd12345', 'BobPwd12345X', 'BobExp123456', 'BobExp123456', False),   # 不一致
    ('bob', 'BobPwd12345', 'BobPwd12345', 'BobExp123456', 'BobExp123456', True),     # 正常
]:
    d = _CreateAccountDialog(fresh)
    d.username_input.setText(un)
    d.pwd_input.setText(p1); d.pwd2_input.setText(p2)
    d.exp_input.setText(ep1); d.exp2_input.setText(ep2)
    d._do_create()
    assert (d.created_username == 'bob') == expect_ok, f'unexpected for {un}'
print('[F3] 引导建号：空文件夹一键建号 + 五组表单校验 通过')

# ─────────────────────────────────────────
# F4: 软删除回收站（数据层 + 视图口径）
# ─────────────────────────────────────────
data = load_vault(vp)
# 删除前：活跃 1、搜索命中、有条目到期
assert count_active_entries(data) == 1
assert len(search_entries(data, 'cloudflare')) == 1
assert len(scan_expiry(data)) == 1

assert delete_entry(data, 'e1')
# 数据仍在，但所有"活跃"口径全部排除
assert len(data['entries']) == 1
assert count_active_entries(data) == 0
assert get_entries_by_category(data, '__all__') == []
assert get_entries_by_category(data, cat['id']) == []
assert search_entries(data, 'cloudflare') == []
assert search_entries(data, 'admin') == []
assert scan_expiry(data) == []
trash = get_deleted_entries(data)
assert len(trash) == 1 and trash[0]['id'] == 'e1'
assert trash[0].get('deleted_at'), '应记录删除时间'
# 导出默认不含回收站条目，recover 全量导出包含
from markdown_export import build_markdown
dec = {**data, 'entries': [{**e, 'fields': [
    {**f, 'value': 'PLAIN' if f.get('type') == 'secret' else f.get('value', '')}
    for f in e.get('fields', [])]} for e in data.get('entries', [])]}
md_gui = build_markdown(dec)
assert 'Cloudflare 主号' not in md_gui, '程序内导出不应包含回收站条目'
md_full = build_markdown(dec, include_deleted=True)
assert 'Cloudflare 主号' in md_full, 'recover 全量导出应包含回收站条目'
# 登录密钥校验不依赖回收站条目
from vault_io import find_first_encrypted_value
assert find_first_encrypted_value(data) is None, '回收站条目不参与登录校验'
# 恢复
assert restore_entry(data, 'e1')
assert count_active_entries(data) == 1
assert get_deleted_entries(data) == []
# 永久删除
delete_entry(data, 'e1')
assert purge_entry(data, 'e1')
assert len(data['entries']) == 0
save_vault(vp, data)
print('[F4] 软删除：全口径过滤/恢复/永久删除/导出区分/登录校验 通过')

print()
print('=== P4 四项功能全部验证通过 ===')
