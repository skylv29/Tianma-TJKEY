# AAD 双实现防漂移一致性测试
# 覆盖：crypto.py 与 recover.py 各有一份 AAD 构造实现
#   （recover.py 为独立分发不依赖 crypto.py，必须手写副本），
#   两处对同一 (version, entry_id, field_id) 必须产出逐字节相同的结果，
#   否则 version 2 的密文在主程序与灾难恢复工具之间会互相解不开。
# 覆盖用例：空 ID、含中文/Unicode 的 ID、缺 ID（None / 键不存在），
#   以及 version 1（无 AAD 语义）的行为一致性。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import (
    AAD_PREFIX as CRYPTO_PREFIX,
    build_field_aad,
    field_aad,
)
from recover import (
    AAD_PREFIX as RECOVER_PREFIX,
    build_field_aad_standalone,
    field_aad_for,
)


def _expect_value_error(fn, *args, label: str):
    """断言调用抛出 ValueError（空/缺 ID 防呆两边必须行为一致）。"""
    try:
        fn(*args)
    except ValueError:
        return
    raise AssertionError(f"{label} 应抛 ValueError: {args!r}")


def _expect_no_error(fn, *args, label: str):
    """断言调用正常返回（不抛异常）。"""
    try:
        return fn(*args)
    except Exception as e:
        raise AssertionError(f"{label} 不应抛异常: {args!r} → {e}") from e


# ─────────────────────────────────────────
# 1. AAD 前缀逐字节一致（漂移的第一道防线）
# ─────────────────────────────────────────
assert isinstance(CRYPTO_PREFIX, bytes) and isinstance(RECOVER_PREFIX, bytes)
assert CRYPTO_PREFIX == RECOVER_PREFIX, (
    f"AAD 前缀漂移: crypto={CRYPTO_PREFIX!r} recover={RECOVER_PREFIX!r}")
print(f'[1] AAD 前缀一致: {CRYPTO_PREFIX!r}')

# ─────────────────────────────────────────
# 2. 正常 ID：含 ASCII / 中文 / Unicode / 分隔符，逐字节一致
# ─────────────────────────────────────────
normal_cases = [
    ("entry_abc123", "fld_001"),                  # 常规 ASCII
    ("条目_云端服务器", "密码_字段"),               # 中文
    ("entry_🚀火箭", "field_ünïcode_Ω"),           # emoji + 组合变音 + 希腊字母
    ("entry|with|pipes", "field|also|pipes"),     # 含分隔符 |（防构造歧义回归）
    ("e", "f"),                                   # 最短非空
]
for eid, fid in normal_cases:
    a = build_field_aad(eid, fid)
    b = build_field_aad_standalone(eid, fid)
    assert isinstance(a, bytes) and isinstance(b, bytes)
    assert a == b, f"正常 ID 产出漂移: {(eid, fid)!r}: {a!r} != {b!r}"
    # 版本分支包装层同样一致：v2 两边都委托到各自 build 且结果相同
    assert field_aad({"version": 2}, eid, fid) == b, \
        f"field_aad v2 与 recover build 漂移: {(eid, fid)!r}"
    assert field_aad_for(2, eid, fid) == a, \
        f"field_aad_for v2 与 crypto build 漂移: {(eid, fid)!r}"
print(f'[2] 正常 ID（ASCII/中文/Unicode/分隔符）共 {len(normal_cases)} 组逐字节一致')

# ─────────────────────────────────────────
# 3. 空 ID：两边 build 与 v2 包装层都必须抛 ValueError
# ─────────────────────────────────────────
empty_cases = [("", "fld_001"), ("entry_abc", ""), ("", "")]
for eid, fid in empty_cases:
    _expect_value_error(build_field_aad, eid, fid, label="crypto.build")
    _expect_value_error(build_field_aad_standalone, eid, fid,
                        label="recover.build")
    _expect_value_error(field_aad, {"version": 2}, eid, fid,
                        label="crypto.field_aad v2")
    _expect_value_error(field_aad_for, 2, eid, fid,
                        label="recover.field_aad_for v2")
print(f'[3] 空 ID 共 {len(empty_cases)} 组：两边一致抛 ValueError')

# ─────────────────────────────────────────
# 4. 缺 ID（None / 键不存在语义同 None）：v2 两边都必须抛 ValueError
# ─────────────────────────────────────────
missing_cases = [(None, "fld_001"), ("entry_abc", None), (None, None)]
for eid, fid in missing_cases:
    _expect_value_error(build_field_aad, eid, fid, label="crypto.build")
    _expect_value_error(build_field_aad_standalone, eid, fid,
                        label="recover.build")
    _expect_value_error(field_aad, {"version": 2}, eid, fid,
                        label="crypto.field_aad v2")
    _expect_value_error(field_aad_for, 2, eid, fid,
                        label="recover.field_aad_for v2")
# 键不存在场景：调用方 field.get("id") 缺键时得到 None，同上用例覆盖；
# 这里额外确认 vault_data 缺 version 键时 crypto 侧按 1 处理不抛
r1 = _expect_no_error(field_aad, {}, "e", "f",
                      label="crypto.field_aad 缺 version 键")
assert r1 is None, "缺 version 键应按 version 1 处理返回 None"
print(f'[4] 缺 ID 共 {len(missing_cases)} 组：v2 两边一致抛 ValueError；'
      f'缺 version 键按 v1 返回 None')

# ─────────────────────────────────────────
# 5. version 1（无 AAD 语义）：两边包装层行为一致（都返回 None），
#    即使 ID 为空/缺也不抛——v1 不校验 ID，与 v2 防呆形成对照
# ─────────────────────────────────────────
v1_cases = [
    ("entry_abc", "fld_001"),
    ("", ""),
    (None, None),
]
for eid, fid in v1_cases:
    r_crypto = _expect_no_error(field_aad, {"version": 1}, eid, fid,
                                label="crypto.field_aad v1")
    r_recover = _expect_no_error(field_aad_for, 1, eid, fid,
                                 label="recover.field_aad_for v1")
    assert r_crypto is None and r_recover is None, \
        f"v1 应返回 None: {(eid, fid)!r}: {r_crypto!r} vs {r_recover!r}"
# version 0 及负数（畸形数据）同样按无 AAD 处理，两边一致
assert field_aad({"version": 0}, "e", "f") is None
assert field_aad_for(0, "e", "f") is None
print(f'[5] version 1/0 共 {len(v1_cases) + 1} 组：两边一致返回 None 且不抛异常')

# ─────────────────────────────────────────
# 6. 端到端对照：同一输入直接交叉验证两份 build 的字节等价
# ─────────────────────────────────────────
all_cases = normal_cases  # 成功路径用例全量交叉
for eid, fid in all_cases:
    assert bytes(build_field_aad(eid, fid)) == \
        bytes(build_field_aad_standalone(eid, fid))
print(f'[6] 端到端交叉 {len(all_cases)} 组全部逐字节相同')

print()
print('=== AAD 双实现一致性验证通过 ===')
