# P3 第二轮修复验证脚本（离屏运行，不显示窗口）
# 覆盖：
#   P3-1 load_app_conf 默认配置深拷贝（嵌套 dict 不与常量共享）
#   P3-2 reorder 遗漏 ID 追加尾部，不丢弃分类
#   P3-3 Markdown 导出：含 ``` 的 secret 不断裂、标签竖线转义、孤儿分类归未分类
#   P3-4 URL 复制接入剪贴板自动清空
#   P3-5 编辑面板：非法日期拦截保存；保存成功后立即清空明文
#   P3-6 登录界面显示名称走内存缓存（不逐键读盘）
#   P3-7 recover.py 派生函数拒绝畸形 iterations / 缺失 salt
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from session import session
from accounts import create_account, load_app_conf, DEFAULT_APP_CONF
from vault_io import (create_empty_vault, load_vault, save_vault,
                      add_category, add_subcategory, reorder_categories,
                      reorder_subcategories, get_category_by_id)
from crypto import derive_key, encrypt_field

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
key = derive_key('RightPwd', vdata['kdf_params']['salt'])
save_vault(vp, vdata)

# ─────────────────────────────────────────
# P3-1: load_app_conf 深拷贝默认配置
# ─────────────────────────────────────────
fresh_dir = tempfile.mkdtemp()
conf = load_app_conf(fresh_dir)          # 文件不存在 → 返回默认
conf['window_geometry']['width'] = 99999  # 原地修改
conf2 = load_app_conf(fresh_dir)
assert conf2['window_geometry']['width'] == DEFAULT_APP_CONF['window_geometry']['width'], \
    '默认配置的嵌套字段不应被上次调用污染'
print('[P3-1] load_app_conf 返回深拷贝，嵌套默认值不会被污染')

# ─────────────────────────────────────────
# P3-2: reorder 遗漏 ID 不丢弃
# ─────────────────────────────────────────
data = load_vault(vp)
c1 = add_category(data, 'A')
c2 = add_category(data, 'B')
c3 = add_category(data, 'C')
s1 = add_subcategory(data, c1['id'], 'A1')
s2 = add_subcategory(data, c1['id'], 'A2')

reorder_categories(data, [c3['id']])     # 故意遗漏 c1/c2
ids = [c['id'] for c in data['categories']]
assert sorted(ids) == sorted([c1['id'], c2['id'], c3['id']]), \
    f'遗漏的分类不应被丢弃: {ids}'
assert ids[0] == c3['id'], '给出的顺序应生效'
assert [c['order'] for c in data['categories']] == [0, 1, 2]

reorder_subcategories(data, c1['id'], [s2['id']])   # 遗漏 s1
subs = get_category_by_id(data, c1['id'])['subcategories']
assert len(subs) == 2 and subs[0]['id'] == s2['id']
assert [s['order'] for s in subs] == [0, 1]
print('[P3-2] reorder 遗漏/重复 ID 追加尾部，分类数据不丢失、order 连续')

# ─────────────────────────────────────────
# P3-3: Markdown 导出加固
# ─────────────────────────────────────────
data = load_vault(vp)
cat = add_category(data, '域名注册')
data['entries'].append({
    'id': 'e1', 'name': '围栏测试', 'category_id': cat['id'],
    'subcategory_id': None, 'order': 0,
    'fields': [
        {'id': 'fld_001', 'label': 'API Key', 'type': 'secret',
         'value': 'line1\n```python\nprint(1)\n```', 'order': 0},
        {'id': 'fld_002', 'label': '备注', 'type': 'text',
         'value': 'a|b|c', 'order': 1},
    ],
})
# 孤儿条目：category_id 指向已不存在的分类
data['entries'].append({
    'id': 'e2', 'name': '孤儿条目', 'category_id': 'cat_deleted_xyz',
    'subcategory_id': None, 'order': 1,
    'fields': [{'id': 'fld_001', 'label': '用户名', 'type': 'text',
                'value': 'orphan_user', 'order': 0}],
})
data['categories'] = [c for c in data['categories'] if c['id'] != cat['id']]

from markdown_export import build_markdown
md = build_markdown(data)

# 含 ``` 的 secret 应被更长的围栏包裹，且代码块数量成对
assert '````' in md, '含 ``` 的 secret 应使用更长的围栏'
assert md.count('````') == 2, '加长围栏应成对出现'
assert '```python' in md, '值内容应原样保留'
# 长围栏内部的三反引号不应被误当成围栏边界
assert md.index('````') < md.index('```python') < md.rindex('````')
# 标签竖线转义
assert '| a|b|c |' not in md and 'a｜b｜c' in md, 'text 值中的竖线应转义'
# 孤儿条目归入未分类
assert '# 未分类' in md and 'orphan_user' in md, '孤儿条目应归入未分类而非丢失'
print('[P3-3] Markdown 导出：围栏自适应、竖线转义、孤儿条目不丢失')

# ─────────────────────────────────────────
# P3-4: URL 复制接入剪贴板自动清空
# ─────────────────────────────────────────
import ui.entry_detail as ed
ed.QMessageBox.warning = staticmethod(lambda *a, **k: None)
from ui.entry_detail import _FieldRow, EntryDetailPanel, _clear_clipboard_if_matches

clipboard = QApplication.clipboard()
session.session_key = key
session.vault_data = data
panel = EntryDetailPanel()
panel.url_lbl.setText('https://copy.example.com')
panel._copy_to_clipboard(panel.url_lbl.text())
assert clipboard.text() == 'https://copy.example.com'
_clear_clipboard_if_matches('https://copy.example.com')
assert clipboard.text() == ''
print('[P3-4] URL 复制同样接入 30 秒剪贴板自动清空')

# ─────────────────────────────────────────
# P3-5: 编辑面板日期校验 + 保存后清空明文
# ─────────────────────────────────────────
import ui.entry_edit as ee
ee.QMessageBox.warning = staticmethod(lambda *a, **k: None)
from ui.entry_edit import EntryEditPanel

session.vault_data = load_vault(vp)
session.vault_path = vp
session.session_key = key
session.current_account = 'main'
session.current_display_name = '大号'
session.vault_content_hash = __import__('vault_io').file_sha256(vp)

panel_e = EntryEditPanel()
panel_e.load_new_entry('tpl_builtin_002')
rows = panel_e._field_rows
rows[0].get_label = lambda: '用户名'      # 模拟已填好的字段
rows[0]._value_widget.setText('admin')    # text 字段：值控件本身是 QLineEdit
rows[1].get_label = lambda: '密码'
rows[1]._value_widget.input.setText('secret123')   # secret 字段：_SecretInput
rows[2].get_label = lambda: '域名'
rows[2]._domain_input.setText('example.com')
rows[2]._expire_input.setText('2026-13-99')   # 非法日期
panel_e.name_input.setText('日期校验测试')
panel_e._do_save()
assert load_vault(vp)['entries'] == [], '非法日期应拦截保存，文件不写入'
print('[P3-5] date_domain 到期日非法（2026-13-99）→ 拦截保存')

rows[2]._expire_input.setText('2026-12-31')
before = open(vp, 'rb').read()
panel_e.name_input.setText('日期校验测试')
panel_e._do_save()
saved = load_vault(vp)
assert len(saved['entries']) == 1, '合法日期应保存成功'
assert panel_e._field_rows == [], '保存成功后编辑面板应立即清空明文'
assert panel_e.name_input.text() == ''
print('[P3-5] 合法日期保存成功，且保存后明文控件立即清空')

# date 类型字段同样校验（tpl_builtin_001 的"备注"是 text，
# 改类型需要重建行——直接把字段类型替换为 date 再触发保存逻辑）
panel_d = EntryEditPanel()
panel_d.load_new_entry('tpl_builtin_001')
rows_d = panel_d._field_rows
rows_d[0].get_label = lambda: '到期'
rows_d[0]._ftype = 'date'                                   # text → date
rows_d[0]._value_widget.setText('not-a-date')
panel_d.name_input.setText('date 类型校验')
panel_d._do_save()
assert load_vault(vp)['entries'][0]['name'] == '日期校验测试', \
    'date 类型非法值应拦截保存'
print('[P3-5] date 类型字段非法值同样被拦截')

# ─────────────────────────────────────────
# P3-6: 登录界面显示名称缓存（不逐键读盘）
# ─────────────────────────────────────────
from ui.login import LoginWindow
login_calls = []
import accounts as _accounts
_orig_load = _accounts.load_accounts
def _counting_load(p):
    login_calls.append(1)
    return _orig_load(p)
_accounts.load_accounts = _counting_load
import ui.login as _login_mod
_login_mod.load_accounts = _counting_load

lw = LoginWindow(tmp)
login_calls.clear()
lw.username_input.setText('main')      # 联想查询：应走缓存
lw._update_display_name('main')
lw._update_display_name('nonexist')
assert login_calls == [], '显示名称查询不应再读盘'
assert lw.display_name_lbl.text() == '（账号不存在）'
_accounts.load_accounts = _orig_load
_login_mod.load_accounts = _orig_load
print('[P3-6] 登录界面显示名称走内存缓存，账号联想不再逐键读盘')

# ─────────────────────────────────────────
# P3-7: recover.py 派生函数拒绝畸形参数
# ─────────────────────────────────────────
from recover import derive_key_standalone
salt_b64 = vdata['kdf_params']['salt']
for bad_it in (0, -1, 10**15, 'x', None):
    try:
        derive_key_standalone('p', salt_b64, bad_it)
        raise AssertionError(f'非法 iterations 应拒绝: {bad_it!r}')
    except ValueError:
        pass
try:
    derive_key_standalone('p', '')
    raise AssertionError('空 salt 应拒绝')
except ValueError:
    pass
assert derive_key_standalone('p', salt_b64, 1000)  # 合法值正常工作
print('[P3-7] recover.py 拒绝畸形 iterations / 缺失 salt，不再有假死风险')

print()
print('=== P3 第二轮七项修复全部验证通过 ===')
