# crypto.py
# TJKEY 加密核心模块
#
# 本模块负责所有加密、解密、密钥派生和密码哈希操作。
# 使用业界标准算法，即使主程序消失，也可用标准 Python 工具恢复数据。
#
# 算法说明：
#   - 字段加密：AES-256-GCM（对称加密，带认证标签，防篡改）
#   - 密钥派生：PBKDF2-HMAC-SHA256，60万次迭代，从登录密码派生 256-bit 密钥
#   - 密码哈希：PBKDF2-HMAC-SHA256（用于存储登录密码和导出密码的验证哈希）
#
# ENC: 格式说明：
#   每个加密的 secret 字段存储为 "ENC:<base64数据>"
#   base64 数据解码后结构为：前12字节=IV，剩余=密文+16字节认证标签

import os
import base64
import hashlib
import secrets
import string

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


# ─────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────

KDF_ITERATIONS = 600_000   # PBKDF2 迭代次数，平衡安全性与性能
KDF_DKLEN = 32             # 派生密钥长度（字节），对应 AES-256
IV_LENGTH = 12             # AES-GCM 推荐 IV 长度（字节）
SALT_LENGTH = 16           # salt 长度（字节）
ENC_PREFIX = "ENC:"        # 加密字段的标识前缀
AAD_PREFIX = b"tjkey-v2|"  # AAD 绑定数据前缀（vault version 2 起启用）

# verify_password 支持的参数白名单：
# accounts.conf 会被云盘同步，存储的哈希串可能被截断或篡改，
# 若不校验参数，非法的 hash_name / iterations 会让验证函数抛异常
# （而不是返回 False），导致登录界面点击无反应
SUPPORTED_KDF_ALGOS = {"pbkdf2"}
SUPPORTED_HASH_NAMES = {"sha256"}
MAX_KDF_ITERATIONS = 10_000_000   # 迭代次数上限（远高于当前的 60 万），
                                  # 防止畸形配置导致每次验证卡死；若未来
                                  # 上调 KDF_ITERATIONS 超过此值需同步修改
MIN_HASH_ITERATIONS = 100_000     # accounts.conf 验证哈希的迭代下限：
                                  # 防止云同步篡改哈希串把迭代数降到极低值
                                  # 实现参数降级（合法哈希始终为 60 万）


# ─────────────────────────────────────────────
# Salt 生成
# ─────────────────────────────────────────────

def generate_salt() -> str:
    """
    生成随机 16 字节 salt，返回 base64 编码字符串。
    用途：
      1. vault 文件的 kdf_params.salt（密钥派生用）
      2. 密码哈希的 salt（存储在 accounts.conf 中）
    每次创建账号时调用一次，之后固定不变。
    """
    raw = os.urandom(SALT_LENGTH)
    return base64.b64encode(raw).decode("utf-8")


# ─────────────────────────────────────────────
# 密钥派生（登录时调用一次）
# ─────────────────────────────────────────────

def derive_key(password: str, salt_b64: str,
               iterations: int = KDF_ITERATIONS) -> bytes:
    """
    从登录密码和 salt 派生 AES-256 加密密钥。

    参数：
        password    - 用户输入的登录密码（明文字符串）
        salt_b64    - base64 编码的 salt（来自 vault 文件的 kdf_params.salt）
        iterations  - PBKDF2 迭代次数，默认取内置常量。
                      登录/重加密时应传入 vault 文件 kdf_params.iterations
                      中记录的值：密钥由"密码+salt+迭代次数"共同决定，
                      未来上调迭代次数后，旧 vault 仍能按其记录值登录。

    返回：
        32 字节的密钥，存入 session.session_key

    异常：
        ValueError - iterations 非法（非整数或超出 1..MAX_KDF_ITERATIONS）

    注意：
        此函数较慢（约 0.3-1 秒，取决于硬件），属于正常现象，
        迭代次数多是为了防止暴力破解。
    """
    if isinstance(iterations, bool) or not isinstance(iterations, int) \
            or not (1 <= iterations <= MAX_KDF_ITERATIONS):
        raise ValueError(f"无效的 KDF 迭代次数：{iterations!r}")

    salt = base64.b64decode(salt_b64)
    key = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt,
        iterations=iterations,
        dklen=KDF_DKLEN,
    )
    return key


# ─────────────────────────────────────────────
# AAD（附加认证数据）构造
# vault version 2 起，密文与 entry_id/field_id 绑定：
# 把条目 A 的密码粘到条目 B 上会被认证标签拒绝，防止字段搬移攻击
# ─────────────────────────────────────────────

def build_field_aad(entry_id: str, field_id: str) -> bytes:
    """
    构造字段级 AAD：b"tjkey-v2|<entry_id>|<field_id>"。

    参数：
        entry_id  - 条目 ID（如 "entry_a1b2c3"）
        field_id  - 字段 ID（如 "fld_001"）

    返回：
        AAD 字节串，作为 AES-GCM 的 additional_data 传入加解密。

    异常：
        ValueError - entry_id / field_id 为空（version 2 防呆：
                     缺 ID 的字段不允许以 v2 语义加解密）
    """
    if not entry_id or not field_id:
        raise ValueError(
            "version 2 要求 entry_id 与 field_id 非空，"
            f"实际: entry_id={entry_id!r}, field_id={field_id!r}")
    return (AAD_PREFIX
            + entry_id.encode("utf-8")
            + b"|"
            + field_id.encode("utf-8"))


def field_aad(vault_data: dict, entry_id, field_id):
    """
    按 vault 版本返回字段 AAD：
      - version < 2（含缺省的旧文件）→ None（v1 无 AAD 语义）
      - version >= 2 → build_field_aad(entry_id, field_id)
        （id 缺失时 raise ValueError，绝不静默按无 AAD 处理）

    调用方统一以 field_aad(session.vault_data, entry["id"], field["id"])
    取值后传给 encrypt_field / decrypt_field，兼容新旧 vault。
    """
    version = vault_data.get("version", 1) if vault_data else 1
    if version < 2:
        return None
    return build_field_aad(entry_id, field_id)


# ─────────────────────────────────────────────
# 字段加密（保存 secret 字段时调用）
# ─────────────────────────────────────────────

def encrypt_field(plaintext: str, session_key: bytes, *,
                  aad: bytes | None) -> str:
    """
    加密单个 secret 字段的值。

    参数：
        plaintext    - 用户输入的明文字符串（如密码、API Key）
        session_key  - 内存中的 32 字节密钥（来自 session.session_key）
        aad          - 附加认证数据；v2 vault 传 field_aad(...) 的结果，
                       v1 vault 传 None。keyword-only 无默认值，
                       强制每个调用点显式声明版本语义。

    返回：
        "ENC:<base64编码的 IV+密文+认证标签>" 格式的字符串，写入 vault 文件

    特性：
        每次调用生成随机 IV，即使相同明文每次加密结果也不同，
        无法通过比较密文判断两个字段是否相同。
    """
    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(session_key)
    # encrypt 返回 密文+认证标签（最后16字节为标签）
    ciphertext_with_tag = aesgcm.encrypt(
        iv, plaintext.encode("utf-8"), aad)
    encoded = base64.b64encode(iv + ciphertext_with_tag).decode("utf-8")
    return ENC_PREFIX + encoded


# ─────────────────────────────────────────────
# 字段解密（点击"显示"或"复制"时调用）
# ─────────────────────────────────────────────

def decrypt_field(encrypted_value: str, session_key: bytes, *,
                  aad: bytes | None = None) -> str:
    """
    解密单个 secret 字段的值。

    参数：
        encrypted_value  - vault 文件中存储的 "ENC:..." 字符串
        session_key      - 内存中的 32 字节密钥
        aad              - 加密时使用的附加认证数据；
                           v1 密文（无 AAD）省略或传 None。

    返回：
        解密后的明文字符串

    异常：
        ValueError     - 如果 encrypted_value 格式不正确
        DecryptError   - 密钥错误、数据被篡改，或 AAD 不匹配
                         （密文被搬到其他 entry/field 位置）

    注意：
        非加密字段（不以 ENC: 开头）直接原样返回，
        调用方无需判断是否需要解密。
    """
    if not encrypted_value.startswith(ENC_PREFIX):
        # 非加密字段，直接返回原值
        return encrypted_value

    encoded = encrypted_value[len(ENC_PREFIX):]

    try:
        raw = base64.b64decode(encoded)
    except Exception:
        raise ValueError("无法解码加密数据，字段值格式错误")

    if len(raw) < IV_LENGTH + 16:
        # 至少需要 12字节IV + 16字节认证标签
        raise ValueError("加密数据长度不足，可能已损坏")

    iv = raw[:IV_LENGTH]
    ciphertext_with_tag = raw[IV_LENGTH:]

    aesgcm = AESGCM(session_key)
    try:
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext_with_tag, aad)
    except InvalidTag:
        raise DecryptError("解密失败：密码错误、数据已损坏或字段位置不匹配")

    return plaintext_bytes.decode("utf-8")


def is_encrypted(value: str) -> bool:
    """判断一个字段值是否是加密格式（以 ENC: 开头）。"""
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


# ─────────────────────────────────────────────
# 自定义异常
# ─────────────────────────────────────────────

class DecryptError(Exception):
    """解密失败异常，密钥错误或数据损坏时抛出。"""
    pass


# ─────────────────────────────────────────────
# 密码生成器
# ─────────────────────────────────────────────

# 字符集：易混淆字符（0/O/o、1/l/I）单独分组，仅在选择"含易混淆字符"时使用
_PW_LOWER = string.ascii_lowercase                      # a-z
_PW_UPPER = string.ascii_uppercase                      # A-Z
_PW_DIGITS = string.digits                              # 0-9
_PW_SYMBOLS = "!@#$%^&*-_=+?"                           # 精选安全符号
_PW_AMBIGUOUS = "0Oo1lI"                                # 易混淆字符


def generate_password(length: int = 16,
                      upper: bool = True,
                      digits: bool = True,
                      symbols: bool = True,
                      avoid_ambiguous: bool = True) -> str:
    """
    生成随机密码（加密安全的 secrets 模块，无偏差采样）。

    参数：
        length           - 密码长度（8..128）
        upper            - 是否包含大写字母
        digits           - 是否包含数字
        symbols          - 是否包含符号
        avoid_ambiguous  - 是否排除易混淆字符（0/O/o、1/l/I）

    返回：
        随机密码字符串（小写字母始终包含）

    保证：
        启用的每一类字符至少出现一次（通过先随机放置保证），其余位置
        从全字符集均匀采样；随机源为 secrets（CSPRNG）。

    异常：
        ValueError - 长度超出 8..128，或长度不足以容纳启用的字符类
    """
    if not (8 <= length <= 128):
        raise ValueError(f"密码长度需在 8..128 之间：{length}")

    groups = [_PW_LOWER]
    if upper:
        groups.append(_PW_UPPER)
    if digits:
        groups.append(_PW_DIGITS)
    if symbols:
        groups.append(_PW_SYMBOLS)

    if avoid_ambiguous:
        groups = ["".join(c for c in g if c not in _PW_AMBIGUOUS)
                  for g in groups]
        # 过滤后可能产生空组（理论上不会：小写去掉易混淆字符后仍有 23 个）
        groups = [g for g in groups if g]

    if not groups:
        # 小写字母始终启用，理论上不可达，防御性保留
        raise ValueError("至少需要启用一类字符")

    if length < len(groups):
        raise ValueError(
            f"密码长度 {length} 不足以容纳 {len(groups)} 类必含字符")

    # 1) 每类字符先各随机放一个，保证"启用的字符类都出现"
    pool_all = "".join(groups)
    chars = [secrets.choice(g) for g in groups]
    chars += [secrets.choice(pool_all) for _ in range(length - len(groups))]

    # 2) Fisher-Yates 洗牌（secrets.randbelow），避免必含字符固定在头部
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]

    return "".join(chars)


# ─────────────────────────────────────────────
# 密码哈希（存储在 accounts.conf，用于验证身份）
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    对密码进行 PBKDF2 哈希，返回存储字符串。

    存储格式：
        "pbkdf2:sha256:600000$<salt_hex>$<hash_hex>"

    用途：
        accounts.conf 中的 password_hash 和 export_password_hash 字段。
        注意：此哈希与 derive_key 使用不同的 salt，相互独立。
        哈希只用于身份验证，不用于加密数据。
    """
    salt_bytes = os.urandom(SALT_LENGTH)
    salt_hex = salt_bytes.hex()
    hash_bytes = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt_bytes,
        iterations=KDF_ITERATIONS,
        dklen=32,
    )
    hash_hex = hash_bytes.hex()
    return f"pbkdf2:sha256:{KDF_ITERATIONS}${salt_hex}${hash_hex}"


def verify_password(password: str, hash_str: str) -> bool:
    """
    验证密码是否与存储的哈希匹配。

    参数：
        password  - 用户输入的待验证密码（明文）
        hash_str  - accounts.conf 中存储的哈希字符串

    返回：
        True  - 密码正确
        False - 密码错误或哈希格式无法解析

    注意：
        使用 secrets.compare_digest 进行常量时间比较，防止计时攻击。
        哈希串的算法与参数先过白名单，任何解析/计算异常都按
        "验证失败"（返回 False）处理，绝不向上抛出。
    """
    try:
        # 解析存储格式："pbkdf2:sha256:600000$salt_hex$hash_hex"
        parts = hash_str.split("$")
        if len(parts) != 3:
            return False

        header, salt_hex, stored_hash_hex = parts
        header_parts = header.split(":")
        if len(header_parts) != 3:
            return False

        algo, hash_name, iterations_str = header_parts
        if algo not in SUPPORTED_KDF_ALGOS or hash_name not in SUPPORTED_HASH_NAMES:
            return False

        iterations = int(iterations_str)
        if not (MIN_HASH_ITERATIONS <= iterations <= MAX_KDF_ITERATIONS):
            return False

        salt_bytes = bytes.fromhex(salt_hex)

        # 用相同参数重新计算哈希（同样放在 try 内：任何环节出错都视为验证失败）
        computed_hash = hashlib.pbkdf2_hmac(
            hash_name=hash_name,
            password=password.encode("utf-8"),
            salt=salt_bytes,
            iterations=iterations,
            dklen=32,
        )
    except Exception:
        return False

    computed_hex = computed_hash.hex()

    # 常量时间比较，防止计时攻击
    return secrets.compare_digest(computed_hex, stored_hash_hex)


# ─────────────────────────────────────────────
# ID 生成工具
# ─────────────────────────────────────────────

def generate_id(prefix: str, length: int = 6) -> str:
    """
    生成带前缀的随机 ID。

    参数：
        prefix  - ID 前缀，如 "entry_"、"cat_"、"sub_"
        length  - 随机部分的字符数，默认 6

    返回：
        如 "entry_a1b2c3"、"cat_x9y8z7"

    用途：
        创建条目、分类、模板时调用。
    """
    alphabet = string.ascii_lowercase + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(length))
    return prefix + random_part


def generate_field_id(existing_ids: list) -> str:
    """
    生成字段 ID（格式 fld_001、fld_002...）。
    根据现有 ID 列表自动递增，避免重复。

    参数：
        existing_ids  - 当前条目中已有的字段 ID 列表

    返回：
        如 "fld_007"
    """
    max_num = 0
    for fid in existing_ids:
        if fid.startswith("fld_"):
            try:
                num = int(fid[4:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"fld_{max_num + 1:03d}"


# ─────────────────────────────────────────────
# 时间戳工具
# ─────────────────────────────────────────────

def now_iso() -> str:
    """返回当前时间的 ISO 8601 格式字符串，如 '2025-06-01T12:30:00'。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ─────────────────────────────────────────────
# 模块自测（直接运行此文件时执行）
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== TJKEY crypto.py 自测 ===\n")

    # 1. 生成 salt
    salt = generate_salt()
    print(f"[1] 生成 salt: {salt}")

    # 2. 密钥派生
    password = "MyTestPassword123"
    key = derive_key(password, salt)
    print(f"[2] 派生密钥 (hex): {key.hex()[:32]}...")

    # 3. 加密字段（v2 AAD 语义）
    plaintext = "super_secret_api_key_xyz"
    aad = build_field_aad("entry_test1", "fld_001")
    encrypted = encrypt_field(plaintext, key, aad=aad)
    print(f"[3] 加密结果: {encrypted[:40]}...")

    # 4. 解密字段
    decrypted = decrypt_field(encrypted, key, aad=aad)
    print(f"[4] 解密结果: {decrypted}")
    assert decrypted == plaintext, "解密结果与原文不符！"
    print("    [OK] 加密/解密一致性验证通过")

    # 4b. AAD 错位负例：同一密文换 entry_id 解密必须失败（字段搬移防护）
    wrong_aad = build_field_aad("entry_other", "fld_001")
    try:
        decrypt_field(encrypted, key, aad=wrong_aad)
        raise AssertionError("AAD 不匹配应抛出 DecryptError！")
    except DecryptError:
        print("    [OK] AAD 错位（字段搬移）被认证标签拒绝")

    # 4c. v1 兼容：无 AAD 加解密往返仍可用（旧文件语义）
    enc_v1 = encrypt_field(plaintext, key, aad=None)
    assert decrypt_field(enc_v1, key) == plaintext
    print("    [OK] v1 无 AAD 往返兼容")

    # 4d. field_aad 版本分支：v1 → None；v2 → AAD；v2 缺 id → 报错
    assert field_aad({"version": 1}, "e", "f") is None
    assert field_aad({}, "e", "f") is None          # 旧文件缺 version 字段
    assert field_aad({"version": 2}, "e", "f") == build_field_aad("e", "f")
    try:
        field_aad({"version": 2}, "", "f")
        raise AssertionError("v2 缺 entry_id 应报错！")
    except ValueError:
        print("    [OK] field_aad 版本分支与 v2 缺 ID 防呆正常")

    # 5. 错误密钥解密（应抛出异常）
    wrong_key = os.urandom(32)
    try:
        decrypt_field(encrypted, wrong_key, aad=aad)
        print("    [FAIL] 错误：应该抛出 DecryptError 但没有！")
    except DecryptError as e:
        print(f"[5] 错误密钥正确触发异常: {e}")
        print("    [OK] 认证标签验证机制正常")

    # 6. 非加密字段直接返回
    plain_value = "not_encrypted_text"
    result = decrypt_field(plain_value, key)
    assert result == plain_value
    print(f"[6] 非加密字段原样返回: {result}")
    print("    [OK] 非加密字段处理正常")

    # 7. 密码哈希
    pwd_hash = hash_password(password)
    print(f"[7] 密码哈希: {pwd_hash[:50]}...")
    assert verify_password(password, pwd_hash), "密码验证失败！"
    assert not verify_password("wrong_password", pwd_hash), "错误密码不应通过验证！"
    print("    [OK] 密码哈希与验证正常")

    # 8. ID 生成
    cat_id = generate_id("cat_")
    entry_id = generate_id("entry_")
    fld_id = generate_field_id(["fld_001", "fld_002", "fld_005"])
    print(f"[8] 生成 ID: {cat_id}, {entry_id}, {fld_id}")
    print("    [OK] ID 生成正常")

    # 9. 时间戳
    ts = now_iso()
    print(f"[9] 当前时间戳: {ts}")

    # 10. 畸形/被篡改的哈希串应返回 False 而不是抛异常
    bad_hashes = [
        "",                                       # 空串
        "not-a-hash",                             # 无 $ 分隔
        "pbkdf2:sha256:600000$xyz$abc",           # 非法 hex salt
        "md5:md5:1$ab$cd",                        # 非法算法名
        "pbkdf2:sha999:600000$ab$cd",             # 非法哈希名
        "pbkdf2:sha256:-5$ab$cd",                 # 负迭代次数
        "pbkdf2:sha256:99999999999999$ab$cd",     # 超上限的迭代次数
    ]
    for bad in bad_hashes:
        assert not verify_password(password, bad), f"畸形哈希应验证失败: {bad!r}"
    print("[10] [OK] 畸形哈希串安全返回 False（不抛异常）")

    print("\n=== 全部测试通过 [OK] ===")
