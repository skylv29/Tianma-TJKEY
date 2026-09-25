# P3 修复验证脚本（离屏运行）
# 覆盖：Markdown 导出统一、check_and_setup 去 忙等、剪贴板自动清空、
#       缺 id 字段唯一 ID、预览块导入
import os, sys, tempfile
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])

from PySide6.QtCore import QTimer
from session import session
from accounts import create_account, write_app_config
from vault_io import (create_empty_vault, load_vault, save_vault,
                      add_category, add_subcategory)
from crypto import derive_key, encrypt_field, decrypt_field, build_field_aad

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, 'vaults'))
create_account(tmp, 'main', '大号', 'RightPwd', 'exp456')
vp = os.path.join(tmp, 'vaults', 'main.vault')
vdata = create_empty_vault(vp, 'main')
key = derive_key('RightPwd', vdata['kdf_params']['salt'])

cat = add_category(vdata, '域名注册')
sub = add_subcategory(vdata, cat['id'], 'Cloudflare')
vdata['entries'].append({
    'id': 'e1', 'name': '测试条目', 'category_id': cat['id'],
    'subcategory_id': sub['id'], 'order': 0,
    'created_at': '2026-01-01T00:00:00', 'updated_at': '2026-01-01T00:00:00',
    'url': 'https://example.com', 'tags': ['主力'],
    'fields': [
        {'id': 'fld_001', 'label': '用户名', 'type': 'text',
         'value': 'admin@example.com', 'order': 0},
        {'id': 'fld_002', 'label': '密码', 'type': 'secret',
         'value': encrypt_field('real_secret', key,
                                aad=build_field_aad('e1', 'fld_002')), 'order': 1},
        {'id': 'fld_003', 'label': 'API Key', 'type': 'secret',
         'value': encrypt_field('sk-abc123', key,
                                aad=build_field_aad('e1', 'fld_003')), 'order': 2},
        {'id': 'fld_004', 'label': '域名', 'type': 'date_domain',
         'value': 'example.com|2026-12-31', 'order': 3},
    ],
})
save_vault(vp, vdata)

# ─────────────────────────────────────────
# 1. Markdown 导出统一：程序内导出与 recover.py 产出完全一致
# ─────────────────────────────────────────
import ui.export_dialog as ed
from markdown_export import build_markdown
from recover import decrypt_all_fields

md_gui = ed._build_markdown(vdata, key)
decrypted, ok, fail = decrypt_all_fields(load_vault(vp), key)
assert ok == 2 and fail == 0, (ok, fail)
md_rec = build_markdown(decrypted)
assert md_gui == md_rec, '两条导出路径产出应完全一致'
assert 'real_secret' in md_gui and 'sk-abc123' in md_gui
assert 'ENC:' not in md_gui
assert '## Cloudflare' in md_gui and 'example.com（到期：2026-12-31）' in md_gui
print('[P3] Markdown 导出统一：GUI 导出与 recover.py 产出逐字一致')

# ─────────────────────────────────────────
# 2. check_and_setup：三种路径
# ─────────────────────────────────────────
from ui.login import check_and_setup, SetupWizard

# 2a. 已有有效配置 → 直接返回，不弹窗
app_dir1 = tempfile.mkdtemp()
write_app_config(app_dir1, tmp)
assert check_and_setup(app_dir1) == tmp
print('[P3] check_and_setup：已配置路径直接返回')

# 2b. 无配置 → 弹引导，自动确认 → 返回路径且写入 app.config
app_dir2 = tempfile.mkdtemp()

def _confirm_wizard():
    for w in QApplication.topLevelWidgets():
        if isinstance(w, SetupWizard):
            w.selected_path = tmp
            QTimer.singleShot(50, w._confirm)

QTimer.singleShot(200, _confirm_wizard)
assert check_and_setup(app_dir2) == tmp
assert open(os.path.join(app_dir2, 'app.config'), encoding='utf-8').read().strip() == tmp
print('[P3] check_and_setup：引导确认 → 返回路径（QEventLoop 阻塞，无忙轮询）')

# 2c. 无配置 → 弹引导，直接关闭 → 返回 None
app_dir3 = tempfile.mkdtemp()

def _close_wizard():
    for w in QApplication.topLevelWidgets():
        if isinstance(w, SetupWizard):
            w.close()

QTimer.singleShot(200, _close_wizard)
assert check_and_setup(app_dir3) is None
print('[P3] check_and_setup：关闭引导窗口 → 返回 None')

# ─────────────────────────────────────────
# 3. 剪贴板自动清空（应用级定时器，行销毁后仍生效；含"不覆盖用户后续复制"守卫）
# ─────────────────────────────────────────
import ui.entry_detail as _ed
from ui.entry_detail import (
    _FieldRow, CLIPBOARD_CLEAR_SECONDS, _clear_clipboard_if_matches,
)
clipboard = QApplication.clipboard()
session.session_key = key
session.vault_data = load_vault(vp)

enc = encrypt_field('clip_secret', key, aad=build_field_aad('e1', 'f1'))

# 捕获 singleShot 调度，验证定时间隔；手动触发回调模拟 30 秒到期
scheduled = []
_orig_single = _ed.QTimer.singleShot
_ed.QTimer.singleShot = lambda ms, cb: scheduled.append((ms, cb))
row = _FieldRow('密码', enc, 'secret', 'f1', entry_id='e1')
row._do_copy()
_ed.QTimer.singleShot = _orig_single

assert clipboard.text() == 'clip_secret'
assert scheduled and scheduled[0][0] == CLIPBOARD_CLEAR_SECONDS * 1000
row.deleteLater()          # 模拟切换条目/锁屏：字段行被销毁
scheduled[0][1]()          # 定时器到期：回调不依赖行实例，仍应执行清空
assert clipboard.text() == ''
print('[P3] 复制后剪贴板 30 秒自动清空（应用级定时器，行销毁不影响）')

row2 = _FieldRow('密码', enc, 'secret', 'f1', entry_id='e1')
row2._do_copy()
clipboard.setText('user copied something else')
_clear_clipboard_if_matches('clip_secret')
assert clipboard.text() == 'user copied something else'
print('[P3] 用户后续复制的内容不会被清空逻辑覆盖')

# ─────────────────────────────────────────
# 4. 缺 id 字段生成唯一 ID
# ─────────────────────────────────────────
vdata['entries'].append({
    'id': 'e2', 'name': '无ID条目', 'category_id': None,
    'subcategory_id': None, 'order': 1, 'fields': [
        {'label': 'A', 'type': 'text', 'value': 'a', 'order': 0},
        {'label': 'B', 'type': 'text', 'value': 'b', 'order': 1},
    ],
})
save_vault(vp, vdata)

import ui.entry_edit as ee
ee.QMessageBox.warning = staticmethod(lambda *a, **k: None)
from ui.entry_edit import EntryEditPanel
session.vault_data = load_vault(vp)
panel = EntryEditPanel()
panel.load_edit_entry('e2')
ids = [r.field_id for r in panel._field_rows]
assert len(ids) == 2 and len(set(ids)) == 2, f'字段 ID 应唯一: {ids}'
print(f'[P3] 缺 id 字段自动生成唯一 ID: {ids}')

# ─────────────────────────────────────────
# 5. main_window 预览块导入可解析（原 encrypt_field 误导入已修）
# ─────────────────────────────────────────
from vault_io import (create_empty_vault as _cev, add_category as _ac,
                      add_subcategory as _as, add_entry as _ae,
                      build_entry_from_template as _bet, save_vault as _sv)
from crypto import derive_key as _dk, encrypt_field as _ef
from markdown_export import restrict_file_permissions
print('[P3] main_window 预览块导入正常，restrict_file_permissions 可用')

print()
print('=== P3 修复全部验证通过 ===')
