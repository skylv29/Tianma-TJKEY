# 迁移完整性测试（固化人工校验项）
# 覆盖：16 条目、18 个 ENC 字段的 version 1 库，混入
#   1 个缺 entry id、1 个缺 field id、2 个 Unicode/emoji ID 字段，
#   执行 v1→v2→逐字段解密→v2→v1→逐字段解密全流程，断言：
#   1. 缺任一 ID 时 v1→v2 抛 VaultFormatError，且异常时文件不半迁移
#      （前后 SHA 一致、version 仍为 1）；
#   2. 补齐 ID 后完整往返，18 个明文按唯一 label 逐一对应
#      （不依赖 ID/顺序配对，repair 不改明文与顺序）；
#   3. Unicode/emoji ID 字段往返后 ID 与明文一致；
#   4. v2 密文与位置绑定（去掉 AAD 解密必须失败）。
# 全程只用 tempfile，不触碰任何真实数据。
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import (
    derive_key, encrypt_field, decrypt_field, field_aad,
    is_encrypted, generate_salt, DecryptError, KDF_ITERATIONS,
)
from vault_io import (
    save_vault, load_vault, file_sha256, migrate_aad_format,
    VaultFormatError,
)

PASSWORD = "TestPwd123!"
N_ENTRIES = 16
N_ENC_FIELDS = 18

# Unicode/emoji ID 字段的固定坐标（构造时写入，往返后按此核对）
UNICODE_FIELDS = {
    "密码_014": ("条目_🚀Ω", "字段_ünï_🔑"),
    "密码_015": ("entry_🚀🚀", "fld_🔑"),
}


def build_v1_vault(vpath: str, key: bytes, salt: str):
    """构造带缺陷注入的 version 1 测试库，返回 label→预期明文 字典。"""
    expected = {}
    enc_seq = 0
    entries = []
    for i in range(N_ENTRIES):
        # 条目 0、1 各带 2 个 secret 字段，其余各 1 个 → 共 18 个 ENC
        n_secret = 2 if i in (0, 1) else 1

        entry_id = f"entry_{i:02d}"
        if i == 5:
            entry_id = None          # 缺陷注入：缺 entry id（键不存在）
        elif i == 12:
            entry_id = "条目_🚀Ω"     # Unicode/emoji ID 条目 1
        elif i == 13:
            entry_id = "entry_🚀🚀"   # Unicode/emoji ID 条目 2

        fields = [
            {"id": f"fld_{i:02d}_u", "label": "用户名", "type": "text",
             "value": f"user_{i:02d}", "order": 0},
        ]
        for j in range(n_secret):
            label = f"密码_{enc_seq:03d}"           # 唯一 label，配对用
            plaintext = f"明文密码第{enc_seq:03d}号🔐"
            expected[label] = plaintext

            field_id = f"fld_{i:02d}_p{j}"
            if i == 8:
                field_id = None       # 缺陷注入：缺 field id（键不存在）
            elif i == 12:
                field_id = "字段_ünï_🔑"
            elif i == 13:
                field_id = "fld_🔑"

            field = {"label": label, "type": "secret",
                     "value": encrypt_field(plaintext, key, aad=None),  # v1 无 AAD
                     "order": j + 1}
            if field_id is not None:
                field["id"] = field_id
            fields.append(field)
            enc_seq += 1

        entry = {
            "name": f"测试条目_{i:02d}", "category_id": None,
            "subcategory_id": None, "order": i,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "fields": fields,
        }
        if entry_id is not None:
            entry["id"] = entry_id
        entries.append(entry)

    assert enc_seq == N_ENC_FIELDS, \
        f"应构造 {N_ENC_FIELDS} 个 ENC 字段，实际 {enc_seq}"
    vault = {
        "version": 1,
        "account": "main",
        "kdf_params": {
            "algorithm": "pbkdf2", "hash": "sha256",
            "iterations": KDF_ITERATIONS, "salt": salt,
        },
        "categories": [],
        "entries": entries,
    }
    save_vault(vpath, vault)
    return expected


def decrypt_all(vpath: str, key: bytes):
    """解密库中全部 ENC 字段，返回 (label→明文 字典, vault dict)。

    配对键用字段唯一 label；v1 按 version 走无 AAD 分支，
    缺 ID 也不会在此处抛错（与 migrate 的 v2 防呆形成对照）。
    """
    data = load_vault(vpath)
    out = {}
    for entry in data.get("entries", []):
        for field in entry.get("fields", []):
            value = field.get("value", "")
            if isinstance(value, str) and is_encrypted(value):
                aad = field_aad(data, entry.get("id"), field.get("id"))
                out[field["label"]] = decrypt_field(value, key, aad=aad)
    return out, data


def expect_upgrade_blocked(vpath: str, key: bytes, sha_before: str, step: str):
    """断言 v1→v2 抛 VaultFormatError 且文件未被半迁移。"""
    try:
        migrate_aad_format(vpath, key, target_version=2)
        raise AssertionError(f"{step}：应抛 VaultFormatError 却成功了")
    except VaultFormatError:
        pass
    sha_after = file_sha256(vpath)
    assert sha_after == sha_before, f"{step}：异常后文件 SHA 应不变（发生了半迁移）"
    data = load_vault(vpath)
    assert data["version"] == 1, \
        f"{step}：异常后 version 应仍为 1，实际 {data['version']}"
    print(f"    [OK] {step}：抛 VaultFormatError，SHA 前后一致，version 仍为 1")


# ─────────────────────────────────────────
# 1. 构造 version 1 测试库（16 条目 / 18 ENC，含 2 处缺 ID + 2 个 Unicode 字段）
# ─────────────────────────────────────────
tmp = tempfile.mkdtemp()
vpath = os.path.join(tmp, "main.vault")
salt = generate_salt()
key = derive_key(PASSWORD, salt)
expected = build_v1_vault(vpath, key, salt)

raw = load_vault(vpath)
n_enc = sum(1 for e in raw["entries"] for f in e["fields"]
            if isinstance(f.get("value"), str) and is_encrypted(f["value"]))
assert len(raw["entries"]) == N_ENTRIES, f"条目数应为 {N_ENTRIES}"
assert n_enc == N_ENC_FIELDS, f"ENC 字段数应为 {N_ENC_FIELDS}，实际 {n_enc}"
missing_entry = [e for e in raw["entries"] if "id" not in e]
missing_field = [f for e in raw["entries"] for f in e["fields"]
                 if "id" not in f]
assert len(missing_entry) == 1, "应恰好注入 1 个缺 entry id"
assert len(missing_field) == 1, "应恰好注入 1 个缺 field id"
assert set(UNICODE_FIELDS) <= set(expected), "Unicode 字段 label 应在预期表内"
print(f"[1] 构造 v1 库：{N_ENTRIES} 条目 / {n_enc} 个 ENC 字段，"
      f"注入缺 entry id×1、缺 field id×1、Unicode ID 字段×2")

# ─────────────────────────────────────────
# 2. 缺 ID 时 v1→v2 必须被拒：抛 VaultFormatError 且不半迁移
#    （dst AAD 预计算在写盘前完成，异常时文件字节级不变）
# ─────────────────────────────────────────
sha_before = file_sha256(vpath)
expect_upgrade_blocked(vpath, key, sha_before, "注入缺陷后的 v1→v2")
# 被拒后 v1 库仍应可完整解密（缺 ID 只挡 v2 语义，不挡 v1 使用）
pre, _ = decrypt_all(vpath, key)
assert pre == expected, "缺陷 v1 库应仍能按 v1 语义完整解密"
print("    [OK] 被拒后原 v1 库 18 个明文仍逐一对应")

# ─────────────────────────────────────────
# 3. 补齐 2 处缺失的 ID（repair 不改明文、不改顺序），再迁移应成功
# ─────────────────────────────────────────
data = load_vault(vpath)
repaired = 0
for entry in data["entries"]:
    if "id" not in entry:
        entry["id"] = "entry_05"       # 构造时被剔除的 ID，原值补回
        repaired += 1
    for field in entry["fields"]:
        if "id" not in field:
            field["id"] = "fld_08_p0"
            repaired += 1
assert repaired == 2, f"应补齐 2 处缺失 ID，实际 {repaired}"
save_vault(vpath, data)
n = migrate_aad_format(vpath, key, target_version=2)
assert n == N_ENC_FIELDS, f"v1→v2 应转换 {N_ENC_FIELDS} 个字段，实际 {n}"
print(f"[2] 补齐 2 处 ID 后 v1→v2 成功，转换 {n} 个字段")

# ─────────────────────────────────────────
# 4. v2 逐字段解密：18 个明文按 label 逐一对应；v2 密文与位置绑定
# ─────────────────────────────────────────
v2, data2 = decrypt_all(vpath, key)
assert data2["version"] == 2, f"迁移后 version 应为 2，实际 {data2['version']}"
assert len(v2) == N_ENC_FIELDS, f"应解出 {N_ENC_FIELDS} 个明文，实际 {len(v2)}"
assert v2 == expected, (
    "v2 往返明文不逐一对应："
    f"缺失={sorted(set(expected) - set(v2))} "
    f"多余={sorted(set(v2) - set(expected))} "
    f"不一致={[k for k in expected if k in v2 and v2[k] != expected[k]]}")
print(f"[3] v2 解密 {len(v2)} 个字段，明文按唯一 label 逐一对应")

# AAD 绑定：任取一个 v2 密文去掉 AAD 解密必须失败（搬移即拒绝）
sample_entry, sample_field = None, None
for e in data2["entries"]:
    for f in e["fields"]:
        if isinstance(f.get("value"), str) and is_encrypted(f["value"]):
            sample_entry, sample_field = e, f
            break
    if sample_entry:
        break
try:
    decrypt_field(sample_field["value"], key, aad=None)
    raise AssertionError("v2 密文无 AAD 解密应失败")
except DecryptError:
    pass
print("    [OK] v2 密文去掉 AAD 解密失败（位置绑定生效）")

# ─────────────────────────────────────────
# 5. v2→v1 回迁：再逐字段解密，明文与 Unicode ID 往返一致
# ─────────────────────────────────────────
n = migrate_aad_format(vpath, key, target_version=1)
assert n == N_ENC_FIELDS, f"v2→v1 应转换 {N_ENC_FIELDS} 个字段，实际 {n}"
v1, data1 = decrypt_all(vpath, key)
assert data1["version"] == 1, f"回迁后 version 应为 1，实际 {data1['version']}"
assert v1 == expected, (
    "v1 往返明文不逐一对应："
    f"缺失={sorted(set(expected) - set(v1))} "
    f"不一致={[k for k in expected if k in v1 and v1[k] != expected[k]]}")
print(f"[4] v2→v1 回迁 {n} 个字段，再解密 {len(v1)} 个明文逐一对应")

for label, (exp_eid, exp_fid) in UNICODE_FIELDS.items():
    found = None
    for e in data1["entries"]:
        for f in e["fields"]:
            if f.get("label") == label:
                found = (e.get("id"), f.get("id"), f.get("value"))
    assert found is not None, f"Unicode 字段 {label} 未找到"
    eid, fid, value = found
    assert eid == exp_eid, f"{label} 条目 ID 往返不一致：{eid!r} != {exp_eid!r}"
    assert fid == exp_fid, f"{label} 字段 ID 往返不一致：{fid!r} != {exp_fid!r}"
    pt = decrypt_field(value, key, aad=field_aad(data1, eid, fid))
    assert pt == expected[label], f"{label} 明文往返不一致：{pt!r}"
print(f"[5] {len(UNICODE_FIELDS)} 个 Unicode/emoji ID 字段：ID 与明文往返一致")

# 顺序核对：repair 与两次迁移都不许改动条目顺序
order = [e.get("name") for e in data1["entries"]]
assert order == [f"测试条目_{i:02d}" for i in range(N_ENTRIES)], \
    f"条目顺序被改动：{order}"
print(f"[6] {N_ENTRIES} 个条目顺序与构造时一致")

print()
print("=== 迁移完整性验证通过 ===")
