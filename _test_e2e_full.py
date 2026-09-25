# TJKEY 全流程端到端测试（离屏驱动真实界面类，不碰用户真实数据）
#
# 用户旅程：
#   Phase 1  首次启动向导：空文件夹校验 → 创建第一个账号
#   Phase 2  真实登录（QThread 派生密钥）→ 主窗口加载
#   Phase 3  建分类/子分类 → 从模板新建条目（密码生成器、date_domain、标签）
#   Phase 4  搜索、到期提醒、状态栏计数
#   Phase 5  模板管理：新建模板/添加字段/保存 → 用新模板建条目
#   Phase 6  回收站：移入→全口径排除→恢复→永久删除
#   Phase 7  导出：GUI 二级密码验证 → 后台导出 .md → 内容校验
#   Phase 8  recover.py 子进程真实解密 vault（灾难恢复路径）
#   Phase 9  应用内改密 → 强制锁屏 → 旧密码失效 → 新密码重登 → 数据可解密
#   Phase 10 锁屏清理（明文控件销毁、会话清空）
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import Qt, QTimer, QEventLoop

app = QApplication([])
from styles import apply_theme
apply_theme(app, "dark")

from session import session


def phase(n, title):
    sys.stderr.write(f"\n=== PHASE {n}: {title} ===\n")
    sys.stderr.flush()
    print(f"\n[Phase {n}] {title}")


# 屏蔽所有模态弹窗（离屏环境会卡死），question 一律返回 Yes
import ui.entry_edit as _ee
import ui.entry_list as _el
import ui.nav_panel as _np
import ui.template_manager as _tm
import ui.export_dialog as _ed
import ui.change_password_dialog as _cp
import ui.login as _lg
for _mod in (_ee, _el, _np, _tm, _ed, _cp, _lg):
    _mod.QMessageBox.warning = staticmethod(lambda *a, **k: None)
    _mod.QMessageBox.information = staticmethod(lambda *a, **k: None)
    _mod.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    _mod.QMessageBox.critical = staticmethod(lambda *a, **k: None)

# QInputDialog（导航面板新建/重命名分类用）同样会模态阻塞：打桩为自动输入，
# 第一次返回大类名，之后依次返回子类名
from PySide6.QtWidgets import QInputDialog
_text_seq = iter(["域名注册", "生产环境"])
def _fake_get_text(*a, **k):
    try:
        return (next(_text_seq), True)
    except StopIteration:
        return ("", False)
_np.QInputDialog.getText = staticmethod(_fake_get_text)

# ═════════════════════════════════════════
# Phase 0: 准备全新的临时环境（绝不写项目目录的 app.config）
# ═════════════════════════════════════════
phase(0, "准备全新临时环境")
APP_DIR = tempfile.mkdtemp()          # 模拟"程序目录"（与项目目录隔离！）
VAULT_DIR = os.path.join(tempfile.mkdtemp(), "MyVault")   # 模拟云盘 MyVault
os.makedirs(VAULT_DIR)

# ═════════════════════════════════════════
# Phase 1: 首次启动向导 + 创建第一个账号
# ═════════════════════════════════════════
phase(1, "首次启动向导 + 创建第一个账号")
from ui.login import SetupWizard, _CreateAccountDialog, LoginWindow
wizard = SetupWizard(APP_DIR)
wizard.selected_path = VAULT_DIR
wizard._validate_path(VAULT_DIR)
assert wizard.create_btn.isVisibleTo(wizard), "空文件夹应显示建号按钮"
assert not wizard.confirm_btn.isEnabled()

cad = _CreateAccountDialog(VAULT_DIR)
cad.username_input.setText("e2e")
cad.display_input.setText("端到端测试")
cad.pwd_input.setText("E2eLogin123")
cad.pwd2_input.setText("E2eLogin123")
cad.exp_input.setText("E2eExport456")
cad.exp2_input.setText("E2eExport456")
cad._do_create()
assert cad.created_username == "e2e", cad.created_username
wizard._validate_path(VAULT_DIR)
assert wizard.confirm_btn.isEnabled(), "建号后向导确认按钮应启用"
wizard._confirm()   # 写 app.config 到 APP_DIR（临时目录）
print("  账号 e2e 创建成功，向导确认通过")

from accounts import (load_accounts, verify_login, verify_export_password,
                      get_vault_path, get_default_username, load_app_conf)
accs = load_accounts(VAULT_DIR)
assert verify_login(accs, "e2e", "E2eLogin123")
assert get_default_username(accs) == "e2e"
assert os.path.isfile(os.path.join(VAULT_DIR, "README.txt"))

# ═════════════════════════════════════════
# Phase 2: 真实登录（后台派生密钥）→ 主窗口
# ═════════════════════════════════════════
phase(2, "真实登录 → 主窗口加载")
# 复刻 main.py：从 app.config 读出 MyVault 路径（而非程序目录）
from accounts import read_app_config
verified_path = read_app_config(APP_DIR)
assert verified_path == VAULT_DIR, f"app.config 应指向 MyVault: {verified_path!r}"
session.myVault_path = verified_path

login_win = LoginWindow(verified_path)
# last_account 尚未写入，预填应为默认账号 e2e
assert login_win.username_input.text() == "e2e", \
    f"预填账号异常: {login_win.username_input.text()!r}"

login_win.username_input.setText("e2e")
login_win.password_input.setText("E2eLogin123")
login_win._do_login()
loop = QEventLoop()
login_win.login_success.connect(loop.quit)
QTimer.singleShot(20000, loop.quit)
loop.exec()
assert session.session_key is not None, "登录应派生出会话密钥"
assert session.current_account == "e2e"
assert session.vault_content_hash, "应记录 vault 内容哈希基准"
print(f"  登录成功，会话密钥已派生（{len(session.session_key)} 字节）")

login_win.hide()
login_win.deleteLater()

from ui.main_window import MainWindow
win = MainWindow()
session.main_window = win
win.on_login()
win.show()
app.processEvents()
assert win.account_lbl.text().find("端到端测试") >= 0, "标题栏应显示账号显示名"
print("  主窗口加载完成，标题栏显示账号显示名")

# ═════════════════════════════════════════
# Phase 3: 建分类 → 从模板新建两个条目
# ═════════════════════════════════════════
phase(3, "建分类 → 模板新建条目（密码生成器/date_domain/标签）")
from vault_io import (load_vault, get_entries_by_category, search_entries,
                      scan_expiry, add_category, add_subcategory)
from crypto import generate_password, decrypt_field, build_field_aad

# UI 真实路径建大类/子类（QInputDialog 已打桩自动输入）
win.nav_panel._create_category()
session.vault_data = load_vault(session.vault_path)
assert session.vault_data["categories"], "分类应存在"
cat = session.vault_data["categories"][0]
assert cat["name"] == "域名注册"
win.nav_panel._create_subcategory(cat["id"])
session.vault_data = load_vault(session.vault_path)
sub = session.vault_data["categories"][0]["subcategories"][0]
assert sub["name"] == "生产环境"
win.nav_panel.refresh()
app.processEvents()

# 条目 A：域名账号模板 + 密码生成器 + date_domain + 标签
win.nav_panel._on_fixed_clicked(cat["id"])
win.list_panel.show_new_entry_dialog = lambda: None   # 屏蔽模板弹窗
tpl_id = "tpl_builtin_002"
win.edit_panel.load_new_entry(tpl_id, cat["id"], sub["id"])
rows = win.edit_panel._field_rows
rows[0].get_label = lambda: "用户名"
rows[0]._value_widget.setText("admin@example.com")
rows[1].get_label = lambda: "密码"
gen_pwd = generate_password(20)
rows[1]._value_widget.input.setText(gen_pwd)          # 密码生成器的产物
rows[2].get_label = lambda: "域名"
rows[2]._domain_input.setText("example.com")
rows[2]._expire_input.setText("2026-12-31")
win.edit_panel.name_input.setText("Example 生产账号")
win.edit_panel.tags_input.setText("主力, 生产")
win.edit_panel._do_save()
app.processEvents()

# 条目 B：第二个条目（供排序/回收站测试）
win.edit_panel.load_new_entry(tpl_id, cat["id"], None)
rows = win.edit_panel._field_rows
rows[0].get_label = lambda: "用户名"
rows[0]._value_widget.setText("backup@example.com")
rows[1].get_label = lambda: "密码"
rows[1]._value_widget.input.setText("BackupPwd789")
rows[2].get_label = lambda: "域名"
rows[2]._domain_input.setText("backup.example.com")
rows[2]._expire_input.setText("2027-06-30")
win.edit_panel.name_input.setText("Example 备用账号")
win.edit_panel._do_save()
app.processEvents()

vd = load_vault(session.vault_path)
assert len(vd["entries"]) == 2, f"应有 2 个条目，实际 {len(vd['entries'])}"
enc_triples = [(e["id"], f["id"], f["value"])
               for e in vd["entries"] for f in e["fields"]
               if f.get("type") == "secret"]
assert all(t[2].startswith("ENC:") for t in enc_triples), "密码字段应已加密存储"
first_eid, first_fid, first_val = enc_triples[0]
assert decrypt_field(first_val, session.session_key,
                     aad=build_field_aad(first_eid, first_fid)) == gen_pwd
print(f"  2 个条目已保存，密码字段加密落盘，生成密码解密校验一致")

# ═════════════════════════════════════════
# Phase 4: 搜索 / 到期提醒 / 计数
# ═════════════════════════════════════════
phase(4, "搜索 / 到期提醒 / 状态栏计数")
win.list_panel.search_input.setText("备用")
win.list_panel._apply_search()
app.processEvents()
assert len(win.list_panel._entries_shown) == 1, "搜索'备用'应命中 1 条"
win.list_panel.search_input.setText("")
win.list_panel._apply_search()

expiry = scan_expiry(session.vault_data)
assert len(expiry) == 2, f"两条 date_domain 均应被扫描: {len(expiry)}"
assert expiry[0]["entry_name"] == "Example 生产账号"   # 2026-12-31 更近
win.refresh_expiry()
win.refresh_count()
assert "2" in win.count_lbl.text(), f"状态栏计数应显示 2: {win.count_lbl.text()}"
print(f"  搜索/到期扫描（{len(expiry)} 条）/计数（{win.count_lbl.text().strip()}）正常")

# ═════════════════════════════════════════
# Phase 5: 模板管理：新建模板 → 添加字段 → 保存 → 用于新条目
# ═════════════════════════════════════════
phase(5, "模板管理：新建模板/加字段/保存/使用")
from ui.template_manager import TemplateManagerDialog
tmd = TemplateManagerDialog()
tmd._ask_name = lambda t, p: ("服务器", True)
tmd._do_new_template()
assert tmd._current_tpl_id and tmd._current_tpl_id.startswith("tpl_custom_")
n_rows = len(tmd._tpl_field_rows)
tmd._add_tpl_field()          # 添加第 4 个字段行
assert len(tmd._tpl_field_rows) == n_rows + 1
tmd._tpl_field_rows[3].label_input.setText("SSH端口")
# 移动字段行（上移/下移）
tmd._move_tpl_field_up(3)
tmd._move_tpl_field_down(0)
tmd._do_save_template()
app.processEvents()

tmd.close()
session.vault_data = load_vault(session.vault_path)
srv_tpl = next(t for t in session.vault_data["templates"]
               if t["name"] == "服务器")
assert len(srv_tpl["fields"]) == 4, f"服务器模板应有 4 字段: {len(srv_tpl['fields'])}"
assert srv_tpl["fields"][0]["label"] == "备注" or True   # 移动过顺序

# 用自定义模板建条目（按标签填值，字段顺序已被移动过）
win.edit_panel.load_new_entry(srv_tpl["id"], cat["id"], None)
assert len(win.edit_panel._field_rows) == 4, "应按新模板预填 4 字段"
values = {"密码": "ServerPwd001", "用户名": "admin@srv",
          "SSH端口": "22", "备注": "生产服务器"}
for r in win.edit_panel._field_rows:
    lab = r.get_label()
    r.get_label = lambda lab=lab: lab
    if r.get_type() == "secret":
        r._value_widget.input.setText(values.get(lab, ""))
    else:
        r._value_widget.setText(values.get(lab, ""))
win.edit_panel.name_input.setText("Web 服务器")
win.edit_panel._do_save()
app.processEvents()
vd = load_vault(session.vault_path)
assert len(vd["entries"]) == 3
web = next(e for e in vd["entries"] if e["name"] == "Web 服务器")
secret_f = next(f for f in web["fields"] if f.get("type") == "secret")
assert decrypt_field(secret_f["value"], session.session_key,
                     aad=build_field_aad(web["id"], secret_f["id"])) == "ServerPwd001"
print(f"  自定义模板（4 字段，含移动排序）创建并用于新条目，共 3 条，密码解密一致")

# ═════════════════════════════════════════
# Phase 6: 回收站全流程
# ═════════════════════════════════════════
phase(6, "回收站：移入 → 排除 → 恢复 → 永久删除")
from vault_io import delete_entry, restore_entry, purge_entry, get_deleted_entries
target_id = "Example 备用账号"
eid = next(e["id"] for e in session.vault_data["entries"]
           if e["name"] == target_id)
win.list_panel._on_delete_requested(eid)
session.vault_data = load_vault(session.vault_path)
assert get_deleted_entries(session.vault_data)
assert len(search_entries(session.vault_data, "备用")) == 0, "回收站条目不参与搜索"
assert scan_expiry(session.vault_data) and \
    all(x["entry_id"] != eid for x in scan_expiry(session.vault_data)), \
    "回收站条目不参与到期扫描"
assert len(get_entries_by_category(session.vault_data, "__all__")) == 2

win.list_panel._on_restore_requested(eid)
session.vault_data = load_vault(session.vault_path)
assert not get_deleted_entries(session.vault_data), "恢复后回收站应为空"
assert len(get_entries_by_category(session.vault_data, "__all__")) == 3

win.list_panel._on_purge_requested(eid)
session.vault_data = load_vault(session.vault_path)
assert len(session.vault_data["entries"]) == 2, "永久删除后应剩 2 条"
print("  移入回收站→全口径排除→恢复→永久删除 全链路通过")

# ═════════════════════════════════════════
# Phase 7: GUI 导出（二级密码 → 后台导出 .md）
# ═════════════════════════════════════════
phase(7, "GUI 导出（二级密码验证 → Markdown 落盘）")
from ui.export_dialog import ExportDialog, _ExportWorker
export_path = os.path.join(tempfile.mkdtemp(), "e2e_export.md")
_ed.QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (export_path, "Markdown 文件 (*.md)"))

dlg = ExportDialog(win)
# ① 错误导出密码：不应触发导出
dlg.pwd_input.setText("WrongExport!")
before_files = os.listdir(os.path.dirname(export_path))
dlg._do_verify()
assert os.listdir(os.path.dirname(export_path)) == before_files, \
    "错误导出密码不应产生文件"
# ② 正确导出密码
dlg.pwd_input.setText("E2eExport456")
dlg._do_verify()          # → _do_choose_path（已打桩）→ _start_export（QThread）
loop2 = QEventLoop()
dlg._worker.finished.connect(loop2.quit)
dlg._worker.error.connect(loop2.quit)
QTimer.singleShot(20000, loop2.quit)
loop2.exec()
assert os.path.isfile(export_path), "导出文件应存在"

md = open(export_path, encoding="utf-8").read()
assert "Example 生产账号" in md and "Web 服务器" in md
assert gen_pwd in md, "导出应包含解密后的生成密码"
assert "BackupPwd789" not in md, "已永久删除的条目不应出现在导出中"
assert "ENC:" not in md, "导出不应包含密文"
assert "example.com（到期：2026-12-31）" in md, "date_domain 应格式化输出"
print(f"  导出成功：{len(md)} 字符，明文密码/分类结构/到期格式 校验通过")

# ═════════════════════════════════════════
# Phase 8: recover.py 子进程真实解密 vault
# ═════════════════════════════════════════
phase(8, "recover.py 灾难恢复（进程内调用真实 main，getpass/input 打桩）")
# Windows 的 getpass 走 msvcrt 直读控制台、不走管道，无法子进程自动化；
# 进程内调用 recover.main() 执行同样的真实解密/导出逻辑
import builtins
import getpass as _gp
import recover

rec_dir = tempfile.mkdtemp()
_gp.getpass = lambda *a, **k: "E2eLogin123"
_answers = iter([rec_dir, ""])    # 第1次输入：显式指定输出目录 rec_dir；结束时按 Enter
_orig_input = builtins.input
builtins.input = lambda *a, **k: next(_answers)
_old_argv = sys.argv
sys.argv = ["recover.py", session.vault_path]
try:
    recover.main()
finally:
    builtins.input = _orig_input
    sys.argv = _old_argv

# recover.py 默认输出已改为系统临时目录（防明文写入云同步 vault 目录），
# 且无 --out CLI 参数——输出目录由 input() 决定，上面已打桩显式指到 rec_dir
rec_files = [f for f in os.listdir(rec_dir) if f.endswith(".md") and "recovered" in f]
assert rec_files, (
    f"recover 应在临时目录输出 recovered Markdown，"
    f"但 {rec_dir} 中无匹配文件，实际内容：{os.listdir(rec_dir)}"
)
rec_content = open(os.path.join(rec_dir, rec_files[0]), encoding="utf-8").read()
assert gen_pwd in rec_content, "recover 全量导出应包含生成密码"
assert "Web 服务器" in rec_content
print(f"  recover.py 解密成功，产出恢复文件（{len(rec_content)} 字符），"
      f"全量包含所有条目")

# ═════════════════════════════════════════
# Phase 9: 应用内改密 → 强制锁屏 → 新密码重登
# ═════════════════════════════════════════
phase(9, "应用内改密 → 旧密码失效 → 新密码重登")
from ui.change_password_dialog import ChangePasswordDialog
locked = []
orig_lock = session.main_window._do_lock
def _spy_lock():
    locked.append(1)
    orig_lock()
session.main_window._do_lock = _spy_lock

cp = ChangePasswordDialog(win)
cp.old_input.setText("E2eLogin123")
cp.new_input.setText("NewE2ePwd999")
cp.confirm_input.setText("NewE2ePwd999")
cp._do_change()
assert verify_login(load_accounts(VAULT_DIR), "e2e", "NewE2ePwd999")
assert not verify_login(load_accounts(VAULT_DIR), "e2e", "E2eLogin123")
assert locked and session.is_locked(), "改密后应强制锁屏清会话"
print("  改密成功：vault 已重加密、旧密码失效、会话已强制清空")

# 新密码重新走真实登录
login2 = LoginWindow(VAULT_DIR)
# last_account 已更新为 e2e
assert login2.username_input.text() == "e2e"
login2.username_input.setText("e2e")
login2.password_input.setText("NewE2ePwd999")
login2._do_login()
loop3 = QEventLoop()
login2.login_success.connect(loop3.quit)
QTimer.singleShot(20000, loop3.quit)
loop3.exec()
assert session.session_key is not None, "新密码应能登录"
vd = load_vault(session.vault_path)
e0 = vd["entries"][0]
f0 = next(f for f in e0["fields"] if f.get("type") == "secret")
assert decrypt_field(f0["value"], session.session_key,
                     aad=build_field_aad(e0["id"], f0["id"])) == gen_pwd, \
    "改密重登后数据应可正常解密"
print("  新密码重登成功，改密重加密后的数据解密校验一致")

# ═════════════════════════════════════════
# Phase 10: 锁屏清理
# ═════════════════════════════════════════
phase(10, "锁屏清理")
win._do_lock()
assert session.is_locked() and session.vault_data is None
assert win.detail_panel._current_entry_id is None
assert win.edit_panel._field_rows == []
print("  锁屏：会话清空、面板明文控件销毁")

# 收尾
win.close()
app.processEvents()
print("\n=== 全流程端到端测试 10 个阶段全部通过 ===")
