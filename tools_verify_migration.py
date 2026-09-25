# -*- coding: utf-8 -*-
# tools_verify_migration.py
# 真实数据迁移后的深度校验（纯只读，不写任何文件，不做任何迁移）
#
# 原理：用主密码分别解密
#   A = 迁移前冷备份文件（--old-file 指定，version 1，无 AAD）
#   B = 当前数据文件（MyVault/vaults/ 下，version 2，字段级 AAD）
# 按 (条目ID, 字段ID) 配对比较明文。明文只在内存比较，全程不打印。
#
# 运行方式（由人工执行，不进自动化测试清单）：
#   python tools_verify_migration.py --myvault D:\MyVault --old-file D:\Backups\myaccount.vault
#   python tools_verify_migration.py --myvault D:\MyVault --old-file D:\Backups\myaccount.vault --vault myaccount.vault
# 缺少必选参数时打印用法并以退出码 2 结束，不会进入密码提示环节。
#
# 退出码：0 = 全部字段解密成功且逐字段明文一致
#         1 = 校验失败或文件缺失；2 = 参数缺失

import argparse
import getpass
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crypto import derive_key, decrypt_field, field_aad


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="TJKEY 迁移深度校验（只读，比较迁移前冷备份与当前数据文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("示例：\n"
                "  python tools_verify_migration.py --myvault D:\\MyVault"
                " --old-file D:\\Backups\\myaccount.vault"),
    )
    parser.add_argument(
        "--myvault", required=True, metavar="DIR",
        help="MyVault 根目录（如 D:\\MyVault），只读访问其 vaults/ 目录",
    )
    parser.add_argument(
        "--old-file", required=True, metavar="PATH",
        help="迁移前冷备份文件路径（version 1 原件，建议放在 MyVault 之外）",
    )
    parser.add_argument(
        "--vault", default=None, metavar="NAME",
        help="当前数据文件名（vaults/ 下），省略时自动探测唯一的 .vault 文件",
    )
    return parser.parse_args(argv)


def _resolve_new_file(myvault, vault_arg):
    """确定迁移后数据文件绝对路径。返回 (path, exit_code)，失败时 path 为 None。"""
    vaults_dir = os.path.join(myvault, "vaults")
    if vault_arg:
        return os.path.join(vaults_dir, vault_arg), None
    try:
        names = sorted(n for n in os.listdir(vaults_dir) if n.endswith(".vault"))
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


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def encrypted_fields(data):
    out = []
    for e in data.get("entries", []):
        for fld in e.get("fields", []):
            v = fld.get("value", "")
            if isinstance(v, str) and v.startswith("ENC:"):
                out.append((str(e.get("id")), str(fld.get("id")), v))
    return out


def decrypt_all(path, password):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    kdf = data.get("kdf_params", {})
    key = derive_key(password, kdf.get("salt", ""), kdf.get("iterations", 600000))
    plains = {}
    fails = []
    for entry_id, field_id, cipher in encrypted_fields(data):
        aad = field_aad(data, entry_id, field_id)
        try:
            plains[(entry_id, field_id)] = decrypt_field(cipher, key, aad=aad)
        except Exception as exc:
            fails.append((entry_id, field_id, type(exc).__name__))
    return data.get("version", 1), plains, fails


def main():
    args = _parse_args()
    old_file = args.old_file
    new_file, err = _resolve_new_file(args.myvault, args.vault)
    if new_file is None:
        return err

    print()
    print("  TJKEY 迁移深度校验（只读）")
    for p in (old_file, new_file):
        if not os.path.isfile(p):
            print(f"  [FAIL] 文件不存在: {p}")
            return 1
    sha_old, sha_new = sha12(old_file), sha12(new_file)
    print(f"  A 迁移前(冷备份) sha12={sha_old}")
    print(f"  B 迁移后(当前)   sha12={sha_new}")

    password = getpass.getpass("  主密码（不回显、不落盘）：")
    if not password:
        print("  [FAIL] 密码为空")
        return 1

    ver_a, pa, fa = decrypt_all(old_file, password)
    ver_b, pb, fb = decrypt_all(new_file, password)
    print(f"  A version={ver_a} 加密字段={len(pa)} 解密失败={len(fa)}")
    print(f"  B version={ver_b} 加密字段={len(pb)} 解密失败={len(fb)}")
    for entry_id, field_id, name in fa + fb:
        print(f"    [解密失败] entry={entry_id} field={field_id} {name}")

    only_a = set(pa) - set(pb)
    only_b = set(pb) - set(pa)
    mismatch = [k for k in (set(pa) & set(pb)) if pa[k] != pb[k]]

    print(f"  配对：共同字段={len(set(pa) & set(pb))} "
          f"仅在A={len(only_a)} 仅在B={len(only_b)} 明文不一致={len(mismatch)}")
    for k in mismatch:
        print(f"    [明文不一致] entry={k[0]} field={k[1]}")
    matched = len(set(pa) & set(pb))
    ok = not fa and not fb and not only_a and not only_b and not mismatch
    del pa, pb

    print()
    if ok:
        print(f"  [OK] 迁移验证通过：{matched} 个加密字段两侧均解密成功且明文逐一对应")
        return 0
    print("  [FAIL] 存在解密失败或明文不一致。立即停止使用该程序，"
          f"把 {os.path.basename(new_file)}.bak（内容 = 冷备份 = 迁移前原文件）"
          f"恢复回 {os.path.basename(new_file)} 后再排查")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  已退出，未写任何文件")
        sys.exit(1)
