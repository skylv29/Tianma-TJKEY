# recover.py
# TJKEY 灾难恢复脚本
#
# 用途：当主程序 vault.exe 无法使用时，手动解密 vault 文件
# 运行方式：python recover.py <vault文件路径>
# 示例：python recover.py "C:\MyVault\vaults\main.vault"
#
# 依赖：cryptography（pip install cryptography）、同目录的
#       markdown_export.py（纯标准库，随程序文件夹一起分发）
# 不依赖 PySide6，任何装了 Python 的电脑均可运行

import os
import sys
import json
import getpass
import hashlib
import base64
import tempfile
from datetime import datetime

# 确保能找到同目录下的 crypto.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
except ImportError:
    print()
    print("  错误：未找到 cryptography 库")
    print("  请先安装：pip install cryptography")
    print()
    sys.exit(1)

try:
    # Markdown 导出使用共享模块（纯标准库，需与 recover.py 同目录）
    from markdown_export import build_markdown, restrict_file_permissions
except ImportError:
    print()
    print("  错误：找不到 markdown_export.py，请与 recover.py 放在同一目录")
    print()
    sys.exit(1)


# ─────────────────────────────────────────────
# 独立实现的加密函数（不依赖 crypto.py，确保独立可用）
# 与 crypto.py 的上限保持一致：畸形/被篡改的 kdf_params 不应让
# PBKDF2 跑到天荒地老（如 iterations 被写成 10^15 时会假死）
MAX_KDF_ITERATIONS = 10_000_000

# AAD 前缀：与 crypto.py 保持字节级一致（version 2 密文绑定 entry/field ID）。
# dist 分发包不含 crypto.py，此处必须本地复制实现，不能 import crypto。
AAD_PREFIX = b"tjkey-v2|"


def build_field_aad_standalone(entry_id, field_id) -> bytes:
    """构造字段级 AAD：b"tjkey-v2|<entry_id>|<field_id>"（与 crypto.py 一致）。"""
    if not entry_id or not field_id:
        raise ValueError(
            "version 2 要求 entry_id 与 field_id 非空，"
            f"实际: entry_id={entry_id!r}, field_id={field_id!r}")
    return (AAD_PREFIX
            + entry_id.encode("utf-8")
            + b"|"
            + field_id.encode("utf-8"))


def field_aad_for(version, entry_id, field_id):
    """按 vault version 计算 AAD：v1 → None；v2 → build_field_aad_standalone。"""
    if version < 2:
        return None
    return build_field_aad_standalone(entry_id, field_id)


def derive_key_standalone(password: str, salt_b64: str, iterations: int = 600000) -> bytes:
    """从密码和 salt 派生 AES-256 密钥（PBKDF2-HMAC-SHA256）。"""
    if not salt_b64:
        raise ValueError("vault 文件缺少 kdf_params.salt，无法派生密钥")
    # 拒绝 bool：isinstance(True, int) 为 True，JSON 的 true 会被误当 1 轮迭代
    if isinstance(iterations, bool) or not isinstance(iterations, int) \
            or not (1 <= iterations <= MAX_KDF_ITERATIONS):
        raise ValueError(f"kdf_params.iterations 非法：{iterations!r}")
    salt = base64.b64decode(salt_b64)
    return hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt,
        iterations=iterations,
        dklen=32,
    )


def decrypt_field_standalone(encrypted_value: str, key: bytes,
                             aad: bytes | None = None) -> str:
    """
    解密单个 ENC: 前缀的字段值。
    aad：version 2 密文传 field_aad_for(...) 的结果；v1 传/省略 None。
    返回明文字符串，若解密失败抛出异常。
    """
    if not encrypted_value.startswith("ENC:"):
        return encrypted_value  # 非加密字段直接返回

    encoded = encrypted_value[4:]
    raw = base64.b64decode(encoded)

    if len(raw) < 12 + 16:
        raise ValueError("加密数据长度不足，可能已损坏")

    iv = raw[:12]
    ciphertext_with_tag = raw[12:]

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, aad)
        return plaintext.decode("utf-8")
    except InvalidTag:
        raise ValueError("解密失败：密码错误、数据已损坏或字段位置不匹配")


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def hr():
    print("─" * 56)


def find_first_secret_field(data: dict):
    """
    找到 vault 中第一个 ENC: 加密字段，返回 (entry_id, field_id, value)。
    version 2 解密需要 ID 构造 AAD；无加密字段则返回 None。
    """
    for entry in data.get("entries", []):
        for field in entry.get("fields", []):
            val = field.get("value", "")
            if isinstance(val, str) and val.startswith("ENC:"):
                return (entry.get("id"), field.get("id"), val)
    return None


def decrypt_all_fields(data: dict, key: bytes) -> tuple[dict, int, int]:
    """
    解密 vault 中所有加密字段（按文件 version 选择 AAD 语义）。

    返回：
        (解密后的 data dict, 成功解密数量, 失败数量)
    """
    import copy
    result = copy.deepcopy(data)
    version = result.get("version", 1)

    success_count = 0
    fail_count = 0

    for entry in result.get("entries", []):
        for field in entry.get("fields", []):
            val = field.get("value", "")
            if isinstance(val, str) and val.startswith("ENC:"):
                try:
                    aad = field_aad_for(version, entry.get("id"),
                                        field.get("id"))
                    field["value"] = decrypt_field_standalone(val, key, aad)
                    success_count += 1
                except Exception as e:
                    field["value"] = f"[解密失败: {e}]"
                    fail_count += 1

    return result, success_count, fail_count


# ─────────────────────────────────────────────
# 输出格式：JSON
# ─────────────────────────────────────────────

def export_json(decrypted_data: dict, output_path: str) -> None:
    """将解密后的完整数据输出为 JSON 文件。"""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(decrypted_data, f, ensure_ascii=False, indent=2)
    restrict_file_permissions(output_path)


# ─────────────────────────────────────────────
# 输出格式：Markdown
# ─────────────────────────────────────────────

def export_markdown(decrypted_data: dict, output_path: str) -> None:
    """
    将解密后的数据输出为 Markdown 文件。
    格式与程序内导出完全一致（共享实现在 markdown_export.py）：
    # 大类 → ## 小类 → ### 条目，secret 字段用代码块，其余用表格。
    灾难恢复场景传 include_deleted=True，全量导出（含回收站条目）。
    """
    content = build_markdown(decrypted_data, include_deleted=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    restrict_file_permissions(output_path)


# ─────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────

def main():
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║           TJKEY  灾难恢复工具                    ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

    # ── 获取 vault 文件路径 ──
    if len(sys.argv) >= 2:
        vault_path = sys.argv[1].strip().strip('"').strip("'")
    else:
        print("  用法：python recover.py <vault文件路径>")
        print("  示例：python recover.py main.vault")
        print()
        vault_path = input("  或直接输入 vault 文件路径：").strip().strip('"').strip("'")

    if not vault_path:
        print("  错误：未指定 vault 文件路径")
        sys.exit(1)

    if not os.path.isfile(vault_path):
        print(f"  错误：文件不存在：{vault_path}")
        sys.exit(1)

    # ── 读取 vault 文件 ──
    hr()
    print(f"  正在读取：{vault_path}")
    try:
        with open(vault_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  错误：vault 文件 JSON 格式损坏：{e}")
        sys.exit(1)
    except OSError as e:
        print(f"  错误：无法读取文件：{e}")
        sys.exit(1)

    # ── 显示基本信息 + 版本门控 ──
    # 缺 version 字段按 1（原始格式）处理；更高的未知版本（更新版程序
    # 创建）本工具无法解密，明确拒绝而不是解出一堆失败字段
    version = data.get("version", 1)
    if version not in (1, 2):
        print(f"  错误：不支持的 Vault 文件版本：{version}，本工具仅支持 1 和 2")
        print("  （该文件可能由更新版本的 TJKEY 创建，请先升级 recover.py）")
        sys.exit(1)
    account = data.get("account", "未知")
    kdf = data.get("kdf_params", {})
    entry_count = len(data.get("entries", []))

    print(f"  文件版本：{version}")
    print(f"  所属账号：{account}")
    print(f"  加密算法：{kdf.get('algorithm', '').upper()}-{kdf.get('hash', '').upper()}")
    print(f"  KDF 迭代：{kdf.get('iterations', '未知'):,} 次")
    print(f"  条目数量：{entry_count} 条")
    hr()

    # ── 检查是否有加密字段 ──
    first = find_first_secret_field(data)
    if first is None:
        print("  提示：此 vault 文件中没有加密字段，将直接导出所有数据。")
        key = None
    else:
        first_eid, first_fid, first_val = first
        # v2 且缺 ID：先明确报错退出，避免在密码重试循环里被误判为密码错
        try:
            verify_aad = field_aad_for(version, first_eid, first_fid)
        except ValueError as e:
            print(f"  错误：{e}")
            sys.exit(1)

        # ── 输入密码 ──
        print("  请输入该账号的登录密码以解密数据：")
        print("  （输入时不显示字符，这是正常的）")
        print()

        max_attempts = 3
        key = None

        for attempt in range(1, max_attempts + 1):
            password = getpass.getpass(f"  登录密码（第 {attempt}/{max_attempts} 次）：")
            if not password:
                print("  密码不能为空")
                continue

            # 派生密钥
            print("  正在验证密码...")
            salt_b64 = kdf.get("salt", "")
            iterations = kdf.get("iterations", 600000)

            try:
                candidate_key = derive_key_standalone(password, salt_b64, iterations)
                # 用第一个加密字段验证密码是否正确（v2 需带 AAD）
                decrypt_field_standalone(first_val, candidate_key, verify_aad)
                key = candidate_key
                print("  [OK] 密码验证通过！")
                break
            except ValueError as e:
                if attempt < max_attempts:
                    print(f"  [FAIL] {e}，请重试")
                else:
                    print(f"  [FAIL] {e}")
                    print("  已达最大重试次数，退出")
                    sys.exit(1)
            except Exception as e:
                print(f"  [FAIL] 密码验证出错：{e}")
                sys.exit(1)

    # ── 解密所有字段 ──
    hr()
    print("  正在解密所有加密字段...")

    if key is not None:
        decrypted_data, ok_count, fail_count = decrypt_all_fields(data, key)
        print(f"  解密成功：{ok_count} 个字段")
        if fail_count > 0:
            print(f"  解密失败：{fail_count} 个字段（数据可能已损坏）")
    else:
        import copy
        decrypted_data = copy.deepcopy(data)
        ok_count = 0
        fail_count = 0

    # ── 确定输出路径 ──
    base_name = os.path.splitext(os.path.basename(vault_path))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_base = f"{base_name}_recovered_{timestamp}"

    # 默认输出到系统临时目录：vault 所在目录往往是云同步文件夹，
    # 明文恢复文件写进去会被自动上传，绝不能作为默认输出位置
    output_dir = tempfile.gettempdir()

    print()
    print(f"  默认输出目录：{output_dir}（系统临时目录）")
    print("  [!] 请勿选择云同步/网盘目录，避免明文密码被自动上传")
    custom_dir = input("  回车使用默认目录，或输入其他路径：").strip().strip('"').strip("'")
    if custom_dir and os.path.isdir(custom_dir):
        output_dir = custom_dir
    elif custom_dir:
        print(f"  目录不存在，使用默认目录")

    json_path = os.path.join(output_dir, output_base + ".json")
    md_path = os.path.join(output_dir, output_base + ".md")

    # ── 输出文件 ──
    hr()
    print("  正在生成输出文件...")

    try:
        export_json(decrypted_data, json_path)
        print(f"  [OK] JSON 文件：{json_path}")
    except Exception as e:
        print(f"  [FAIL] JSON 输出失败：{e}")

    try:
        export_markdown(decrypted_data, md_path)
        print(f"  [OK] Markdown 文件：{md_path}")
    except Exception as e:
        print(f"  [FAIL] Markdown 输出失败：{e}")

    # ── 完成提示 ──
    hr()
    print()
    print("  [OK] 恢复完成！")
    print()
    print("  [!]  重要提示：")
    print("  · 输出文件包含所有明文密码，请妥善保管")
    print("  · 阅读完毕后建议立即删除这两个文件")
    print("  · 不要将这两个文件移动到云同步文件夹或上传任何云服务")
    print()
    hr()

    input("  按 Enter 退出...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  已退出（Ctrl+C）\n")
        sys.exit(0)
