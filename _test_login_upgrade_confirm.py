# 登录升版"先确认"回归测试（离屏运行，不碰用户真实数据）
# 覆盖 ui/login.py _on_derive_finished 中 version 1 → 2 的确认分支：
#   1. 取消确认（点 No）→ 不发射 login_success、session 被清空、
#      vault/app.conf/accounts.conf 零字节改动、version 仍为 1；
#   2. 确认期间外部改写 vault 再返回 Yes → 确认后哈希复核拦截、
#      session 已锁、不发射 login_success、不进入 migrate；
#   3. 桩返回 Rejected/0（模拟点 X）→ 与取消相同的安全路径；
#   4. 确认升级 → 发射 login_success、文件升为 version 2、
#      全部加密字段可用派生密钥 + AAD 解密、双 conf SHA 不变。
# 全程只用 tempfile，通过打桩 QMessageBox.question 模拟用户点击。
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance() or QApplication([])

from session import session
from accounts import (
    create_account, get_app_conf_path, get_accounts_path, update_app_conf,
)
from vault_io import (
    create_empty_vault, load_vault, save_vault, file_sha256,
    migrate_aad_format,
)
from crypto import (
    derive_key, encrypt_field, decrypt_field, is_encrypted, build_field_aad,
)

import ui.login as _lg

PASSWORD = "RightPwd123"


def _prefill_session(vault_path: str, vault_data: dict):
    """复刻 _do_login 在派生密钥前写入的会话状态。"""
    session.myVault_path = VAULT_DIR
    session.current_account = "main"
    session.current_display_name = "大号"
    session.vault_path = vault_path
    session.vault_data = vault_data
    session.vault_content_hash = file_sha256(vault_path)


def _conf_shas():
    """app.conf 与 accounts.conf 的内容 SHA（文件不存在时为 None）。"""
    return (
        file_sha256(get_app_conf_path(VAULT_DIR)),
        file_sha256(get_accounts_path(VAULT_DIR)),
    )


# ─────────────────────────────────────────
# 0. 临时 MyVault + 账号 + version 1 数据文件（含 1 个 ENC 字段）
# ─────────────────────────────────────────
VAULT_DIR = tempfile.mkdtemp()
os.makedirs(os.path.join(VAULT_DIR, "vaults"))
create_account(VAULT_DIR, "main", "大号", PASSWORD, "exp456")
vp = os.path.join(VAULT_DIR, "vaults", "main.vault")

# 预写 app.conf（last_account 已是 main）：确认路径末尾的
# update_app_conf(last_account=main) 内容不变 → SHA 前后一致可断言
update_app_conf(VAULT_DIR, last_account="main")

# 先按 v2 建库并写入一个加密字段，再降级为 v1，模拟真实旧文件
vdata = create_empty_vault(vp, "main")
key = derive_key(PASSWORD, vdata["kdf_params"]["salt"])
vdata["entries"].append({
    "id": "e1", "name": "测试条目", "category_id": None,
    "subcategory_id": None, "order": 0,
    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
    "fields": [
        {"id": "fld_001", "label": "密码", "type": "secret",
         "value": encrypt_field("secret_before_upgrade", key,
                                aad=build_field_aad("e1", "fld_001")),
         "order": 0},
    ],
})
save_vault(vp, vdata)
migrate_aad_format(vp, key, target_version=1)
pre = load_vault(vp)
assert pre["version"] == 1, f"前置应为 version 1，实际 {pre['version']}"
print(f"[0] 构造 v1 数据文件：{vp}")

login_win = _lg.LoginWindow(VAULT_DIR)
emitted = []
login_win.login_success.connect(lambda: emitted.append(1))

# ─────────────────────────────────────────
# 1. 取消确认（点 No）：不登录、三文件零字节改动
# ─────────────────────────────────────────
sha_before = file_sha256(vp)
assert sha_before, "应能计算文件 SHA"
conf_before = _conf_shas()

_lg.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)

emitted.clear()
_prefill_session(vp, load_vault(vp))
login_win._on_derive_finished(key, "main", {})

assert not emitted, "取消升级后不应发射 login_success"
assert session.is_locked(), "取消升级后 session 应被清空"
sha_after = file_sha256(vp)
assert sha_after == sha_before, (
    f"取消升级后文件应零字节改动：SHA {sha_before} → {sha_after}")
assert _conf_shas() == conf_before, (
    f"取消升级后 app.conf/accounts.conf 应零字节改动："
    f"{conf_before} → {_conf_shas()}")
still_v1 = load_vault(vp)
assert still_v1["version"] == 1, (
    f"取消升级后 version 应仍为 1，实际 {still_v1['version']}")
print("[1] 取消确认：未登录、session 已清空、vault 与双 conf SHA 不变且 version 仍为 1")

# ─────────────────────────────────────────
# 2. 确认期间外部改写 vault 再返回 Yes：哈希复核拦截
# ─────────────────────────────────────────
sha_before_mut = file_sha256(vp)
conf_before_mut = _conf_shas()


def _mutate_then_yes(*_a, **_k):
    """桩：模拟云盘在确认框阻塞期间改写 vault，再模拟用户点「是」。"""
    with open(vp, "ab") as f:
        f.write(b"\n")
    return QMessageBox.Yes


_lg.QMessageBox.question = staticmethod(_mutate_then_yes)

emitted.clear()
_prefill_session(vp, load_vault(vp))
login_win._on_derive_finished(key, "main", {})

assert not emitted, "确认期间外部改写后不应发射 login_success"
assert session.is_locked(), "确认期间外部改写后 session 应被清空"
mutated_hash = file_sha256(vp)
assert mutated_hash != sha_before_mut, "桩应已改写 vault（SHA 变化）"
post_mut = load_vault(vp)
assert post_mut["version"] == 1, (
    "确认期间外部改写被拦截后不应进入 migrate，version 应仍为 1，"
    f"实际 {post_mut['version']}")
assert _conf_shas() == conf_before_mut, (
    f"拦截路径不应改写 app.conf/accounts.conf："
    f"{conf_before_mut} → {_conf_shas()}")
print("[2] 确认期间外部改写：哈希复核拦截、session 已锁、未进入 migrate、双 conf 不变")

# ─────────────────────────────────────────
# 3. 桩返回 Rejected/0（模拟点 X）：走取消安全路径
# ─────────────────────────────────────────
sha_before_x = file_sha256(vp)
conf_before_x = _conf_shas()

_lg.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Rejected)

emitted.clear()
_prefill_session(vp, load_vault(vp))
login_win._on_derive_finished(key, "main", {})

assert not emitted, "Rejected/0 后不应发射 login_success"
assert session.is_locked(), "Rejected/0 后 session 应被清空"
sha_after_x = file_sha256(vp)
assert sha_after_x == sha_before_x, (
    f"Rejected/0 后 vault 应零字节改动：SHA {sha_before_x} → {sha_after_x}")
assert _conf_shas() == conf_before_x, (
    f"Rejected/0 后 app.conf/accounts.conf 应零字节改动："
    f"{conf_before_x} → {_conf_shas()}")
still_v1_x = load_vault(vp)
assert still_v1_x["version"] == 1, (
    f"Rejected/0 后 version 应仍为 1，实际 {still_v1_x['version']}")
print("[3] Rejected/0（点 X）：未登录、session 已清空、三文件 SHA 不变")

# ─────────────────────────────────────────
# 4. 确认升级：登录成功、升为 version 2、字段可解密
# ─────────────────────────────────────────
conf_before_yes = _conf_shas()

_lg.QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

emitted.clear()
_prefill_session(vp, load_vault(vp))
login_win._on_derive_finished(key, "main", {})

assert emitted, "确认升级后应发射 login_success"
assert session.session_key == key, "确认升级后 session_key 应保留"
post = load_vault(vp)
assert post["version"] == 2, (
    f"确认升级后 version 应为 2，实际 {post['version']}")
assert file_sha256(vp) != sha_before, "确认升级后文件应被重写"
assert file_sha256(get_accounts_path(VAULT_DIR)) == conf_before_yes[1], (
    "确认升级不应改写 accounts.conf")
assert file_sha256(get_app_conf_path(VAULT_DIR)) == conf_before_yes[0], (
    f"确认升级不应改写 app.conf（last_account 已预写为 main）："
    f"{conf_before_yes[0]} → {file_sha256(get_app_conf_path(VAULT_DIR))}")

# 全部 ENC 字段按 version 2 + AAD 解密，明文与升级前一致
decrypted = {}
for entry in post.get("entries", []):
    for field in entry.get("fields", []):
        value = field.get("value", "")
        if isinstance(value, str) and is_encrypted(value):
            pt = decrypt_field(
                value, key,
                aad=build_field_aad(entry.get("id"), field.get("id")))
            decrypted[field["label"]] = pt
assert decrypted.get("密码") == "secret_before_upgrade", (
    f"升级后字段解密不一致：{decrypted!r}")
print("[4] 确认升级：登录成功、version 升为 2、ENC 字段 AAD 解密一致、双 conf 不变")

login_win.hide()
login_win.deleteLater()

print()
print("=== 登录升版先确认验证通过 ===")
