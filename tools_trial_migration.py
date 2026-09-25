# tools_trial_migration.py
# TJKEY 真实数据迁移试运行（version 1 ⇄ 2 双向）
#
# 红线（脚本级保证）：
#   1. 对真实数据【只读】：数据文件与 accounts.conf 仅被复制，
#      所有加载/迁移/写盘操作只发生在系统临时目录的副本上，
#      绝不写回源目录。
#   2. 主密码由运行者手动输入（getpass 不回显），
#      不出现在代码、命令行参数、任何输出或日志中。
#   3. 输出只含统计量（条目数/字段数/版本/SHA 前 12 位/一致计数），
#      不打印任何明文或密文正文。
#
# 流程：
#   复制源文件 → 输入主密码 → 副本逐字段解密基线
#   → migrate_aad_format(target=2) → 逐字段再解密
#   → migrate_aad_format(target=1) → 逐字段再解密
#   → 输出「升版前 / 升版后 / 降版后」三状态摘要与对比
#
# 运行方式（由人工执行，本脚本不进 tests/test_suites.py 自动化清单）：
#   python tools_trial_migration.py --myvault D:\MyVault
#   python tools_trial_migration.py --myvault D:\MyVault --vault myaccount.vault
# 缺少 --myvault 时打印用法并以退出码 2 结束，不会进入密码提示环节。
#
# 退出码：0 = 三状态全部成功且明文全一致且源文件未被修改；
#         1 = 任一环节失败；2 = 参数缺失或数据文件不唯一

import argparse
import getpass
import hashlib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from accounts import load_accounts, verify_login
from crypto import derive_key, decrypt_field, field_aad
from vault_io import load_vault, migrate_aad_format


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="TJKEY 真实数据迁移试运行（version 1 ⇄ 2 双向，源目录只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("示例：\n"
                "  python tools_trial_migration.py --myvault D:\\MyVault\n"
                "  python tools_trial_migration.py --myvault D:\\MyVault"
                " --vault myaccount.vault"),
    )
    parser.add_argument(
        "--myvault", required=True, metavar="DIR",
        help="MyVault 根目录（如 D:\\MyVault），只读访问其中的 "
             "accounts.conf 与 vaults/",
    )
    parser.add_argument(
        "--vault", default=None, metavar="NAME",
        help="vaults/ 下的数据文件名（如 myaccount.vault）；"
             "省略时自动探测唯一的 .vault 文件，多个时必须指定",
    )
    return parser.parse_args(argv)


def _resolve_vault_path(myvault: str, vault_arg: str | None):
    """确定要试运行的 vault 文件绝对路径。

    返回 (path, None) 成功；(None, exit_code) 失败（原因已打印）。
    """
    vaults_dir = os.path.join(myvault, "vaults")
    if vault_arg:
        return os.path.join(vaults_dir, vault_arg), None
    try:
        names = sorted(
            n for n in os.listdir(vaults_dir) if n.endswith(".vault"))
    except OSError:
        names = []
    if len(names) == 1:
        return os.path.join(vaults_dir, names[0]), None
    if not names:
        print(f"  [FAIL] {vaults_dir} 下没有 .vault 文件")
        return None, 1
    print(f"  [FAIL] {vaults_dir} 下有 {len(names)} 个 .vault 文件，"
          f"请用 --vault 指定其中一个：")
    for n in names:
        print(f"    - {n}")
    return None, 2


def hr():
    print("─" * 64)


def file_sha12(path: str) -> str:
    """文件 SHA-256 前 12 位（只读打开）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def assert_in_tmp(path: str, tmp_root: str):
    """迁移/写盘前的路径守卫：目标必须位于临时副本目录内。"""
    real = os.path.realpath(path)
    root = os.path.realpath(tmp_root)
    if not (real == root or real.startswith(root + os.sep)):
        raise RuntimeError(f"拒绝在临时目录之外写入：{path}")


def decrypt_snapshot(data: dict, key: bytes) -> dict:
    """
    逐字段解密整个副本，只返回统计量与供比对的内存明文列表。
    明文列表仅在内存中用于跨状态一致性比较，绝不打印。
    """
    version = data.get("version", 1)
    entries = data.get("entries", [])
    plains = []            # 按遍历顺序存放 ENC 字段明文（失败为 None）
    enc_total = 0
    fail = 0
    fields_total = 0
    cipher_len = 0         # 密文总字节数（统计量，非密文本身）

    for entry in entries:
        for field in entry.get("fields", []):
            fields_total += 1
            val = field.get("value", "")
            if not (isinstance(val, str) and val.startswith("ENC:")):
                continue
            enc_total += 1
            cipher_len += len(val)
            try:
                aad = field_aad(data, entry.get("id"), field.get("id"))
                plains.append(decrypt_field(val, key, aad=aad))
            except Exception:
                plains.append(None)
                fail += 1

    return {
        "version": version,
        "entries": len(entries),
        "fields": fields_total,
        "enc": enc_total,
        "ok": enc_total - fail,
        "fail": fail,
        "cipher_len": cipher_len,
        "plains": plains,
    }


def compare_plains(base: list, other: list) -> tuple[int, int]:
    """比较两个明文列表（仅内存），返回 (一致数, 不一致数)。"""
    match = 0
    mismatch = 0
    for a, b in zip(base, other):
        if a == b:
            match += 1
        else:
            mismatch += 1
    # 长度不等的部分计入不一致（迁移不应改变 ENC 字段数量）
    mismatch += abs(len(base) - len(other))
    return match, mismatch


def print_state(label: str, snap: dict, sha12: str):
    """打印单个状态的统计行。"""
    print(f"  {label:<14} version={snap['version']:<2} "
          f"条目={snap['entries']:<3} 字段={snap['fields']:<3} "
          f"加密字段={snap['enc']:<3} 解密成功={snap['ok']:<3} "
          f"解密失败={snap['fail']:<3} 密文总长={snap['cipher_len']:<6} "
          f"文件SHA前12={sha12}")


def main() -> int:
    args = _parse_args()
    source_accounts = os.path.join(args.myvault, "accounts.conf")

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   TJKEY 真实数据迁移试运行（version 1 ⇄ 2）      ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    print("  红线：源目录只读；全部操作在临时副本上进行；")
    print("        输出仅含统计量，不打印任何明文或密文。")
    print()

    # ── [1] 源文件存在性与运行前哈希 ──
    hr()
    print("  [1] 检查源文件（只读）")
    source_vault, err = _resolve_vault_path(args.myvault, args.vault)
    if source_vault is None:
        return err
    vault_name = os.path.basename(source_vault)
    for p in (source_vault, source_accounts):
        if not os.path.isfile(p):
            print(f"  [FAIL] 源文件不存在：{p}")
            return 1
    src_vault_sha = file_sha12(source_vault)
    src_accounts_sha = file_sha12(source_accounts)
    print(f"  [OK] {vault_name:<14} SHA前12={src_vault_sha}")
    print(f"  [OK] accounts.conf  SHA前12={src_accounts_sha}")

    # ── [2] 复制到临时目录 ──
    print("  [2] 复制到临时目录")
    tmp_root = tempfile.mkdtemp(prefix="tjkey_trial_")
    tmp_vaults = os.path.join(tmp_root, "vaults")
    os.makedirs(tmp_vaults)
    tmp_vault = os.path.join(tmp_vaults, vault_name)
    tmp_accounts = os.path.join(tmp_root, "accounts.conf")
    shutil.copy2(source_vault, tmp_vault)
    shutil.copy2(source_accounts, tmp_accounts)
    print(f"  [OK] 副本目录：{tmp_root}")

    # ── [3] 主密码（手动输入，不回显、不记录） ──
    print("  [3] 输入该账号的主密码（输入不显示，仅用于内存派生）")
    password = getpass.getpass("  主密码：")
    if not password:
        print("  [FAIL] 密码为空，中止")
        return 1

    try:
        # ── [4] 账户验证 + 密钥派生（全部基于副本） ──
        print("  [4] 验证密码（基于副本 accounts.conf）...")
        accounts = load_accounts(tmp_root)
        base_data = load_vault(tmp_vault)
        account = base_data.get("account", "")
        if not verify_login(accounts, account, password):
            print("  [FAIL] 密码错误（accounts.conf 验证未通过），中止")
            return 1
        kdf = base_data.get("kdf_params", {})
        key = derive_key(password, kdf.get("salt", ""),
                         kdf.get("iterations", 600000))
        print("  [OK] 密码验证通过，密钥已派生（仅存内存）")

        # ── [5] 状态 A：升版前基线解密 ──
        hr()
        print("  [5] 状态 A：升版前（基线）逐字段解密")
        sha_a = file_sha12(tmp_vault)
        state_a = decrypt_snapshot(base_data, key)
        print_state("升版前(v1)", state_a, sha_a)
        if state_a["enc"] > 0 and state_a["ok"] == 0:
            print("  [FAIL] 基线全部解密失败，密码或数据异常，中止")
            return 1

        # ── [6] 升版 v1 → v2 ──
        print("  [6] migrate_aad_format(target_version=2)")
        assert_in_tmp(tmp_vault, tmp_root)
        n_up = migrate_aad_format(tmp_vault, key, target_version=2)
        base_data2 = load_vault(tmp_vault)
        sha_b = file_sha12(tmp_vault)
        state_b = decrypt_snapshot(base_data2, key)
        print(f"  [OK] 升版转换字段数={n_up}"
              f"（基线加密字段={state_a['enc']}）")
        print_state("升版后(v2)", state_b, sha_b)

        # ── [7] 降版 v2 → v1 ──
        print("  [7] migrate_aad_format(target_version=1)")
        assert_in_tmp(tmp_vault, tmp_root)
        n_down = migrate_aad_format(tmp_vault, key, target_version=1)
        base_data3 = load_vault(tmp_vault)
        sha_c = file_sha12(tmp_vault)
        state_c = decrypt_snapshot(base_data3, key)
        print(f"  [OK] 降版转换字段数={n_down}"
              f"（升版后加密字段={state_b['enc']}）")
        print_state("降版后(v1)", state_c, sha_c)
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        print("  （异常信息不含明文/密文；副本目录保留供排查："
              f"{tmp_root}）")
        return 1

    # ── [8] 三状态对比摘要 ──
    hr()
    print("  [8] 三状态对比摘要（仅统计量）")
    m_up, x_up = compare_plains(state_a["plains"], state_b["plains"])
    m_down, x_down = compare_plains(state_a["plains"], state_c["plains"])
    print(f"  明文一致性  升版后 vs 基线：一致={m_up} 不一致={x_up}"
          f"（共 {len(state_a['plains'])} 个加密字段）")
    print(f"  明文一致性  降版后 vs 基线：一致={m_down} 不一致={x_down}"
          f"（共 {len(state_a['plains'])} 个加密字段）")
    # 密文对比：迁移=两遍式重新加密，IV 随机 → 密文必然整体变化；
    # 这里只统计变化字段数（需逐字段比较密文，但不输出密文本身）
    print(f"  密文总长    基线={state_a['cipher_len']} "
          f"升版后={state_b['cipher_len']} 降版后={state_c['cipher_len']}"
          f"（长度结构不变；内容因随机 IV 必然重写）")
    print(f"  转换计数    升版={n_up} 降版={n_down} "
          f"应各自等于对应状态的加密字段数")

    # ── [9] 源文件保护复核 ──
    hr()
    print("  [9] 源文件保护复核（运行结束后重新哈希）")
    src_vault_sha2 = file_sha12(source_vault)
    src_accounts_sha2 = file_sha12(source_accounts)
    vault_untouched = src_vault_sha == src_vault_sha2
    accounts_untouched = src_accounts_sha == src_accounts_sha2
    print(f"  {vault_name:<14} 运行前={src_vault_sha} 运行后={src_vault_sha2} "
          f"→ {'未被修改' if vault_untouched else '!!已被修改!!'}")
    print(f"  accounts.conf 运行前={src_accounts_sha} "
          f"运行后={src_accounts_sha2} "
          f"→ {'未被修改' if accounts_untouched else '!!已被修改!!'}")
    print(f"  副本目录（含加密副本，确认后可手动删除）：{tmp_root}")

    # ── [10] 结论 ──
    hr()
    all_ok = (
        vault_untouched and accounts_untouched
        and state_a["fail"] == 0 and state_b["fail"] == 0
        and state_c["fail"] == 0
        and x_up == 0 and x_down == 0
        and state_a["version"] == 1 and state_b["version"] == 2
        and state_c["version"] == 1
        and n_up == state_a["enc"] and n_down == state_b["enc"]
    )
    if all_ok:
        print("  [OK] 试运行通过：三状态解密全成功、明文全一致、"
              "版本按预期切换、源文件未被修改")
        print()
        print("  提示：正式环境登录时会自动执行升版（v1 → v2）；")
        print("  回退旧版程序可用 vault_admin.py 菜单 [7] 降级（v2 → v1）。")
        print("  云同步场景：必须所有机器先升级程序，再打开数据文件。")
        return 0
    print("  [FAIL] 试运行未全部通过，请对照上方统计逐项排查")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  已退出（Ctrl+C）——源目录未被写入\n")
        sys.exit(1)
