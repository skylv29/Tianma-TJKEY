# vault_io.py
# TJKEY Vault 文件读写模块
#
# 负责 .vault 文件的创建、读取、保存操作。
# .vault 文件本质是 JSON，明文存结构信息，secret 字段以 ENC: 前缀存储。
#
# 内置模板定义也在本文件中，确保新建 vault 时自动包含5个标准模板。

import json
import os
import hashlib
import copy
from datetime import datetime, date

from crypto import (
    generate_salt, generate_id, now_iso, KDF_ITERATIONS,
    derive_key, encrypt_field, decrypt_field, is_encrypted, DecryptError,
    build_field_aad, field_aad,
)


# ─────────────────────────────────────────────
# 内置模板定义（只改不删）
# ─────────────────────────────────────────────

BUILTIN_TEMPLATES = [
    {
        "id": "tpl_builtin_001",
        "name": "通用账号",
        "is_builtin": True,
        "fields": [
            {"label": "用户名", "type": "text"},
            {"label": "密码",   "type": "secret"},
            {"label": "备注",   "type": "text"},
        ],
    },
    {
        "id": "tpl_builtin_002",
        "name": "域名账号",
        "is_builtin": True,
        "fields": [
            {"label": "用户名", "type": "text"},
            {"label": "密码",   "type": "secret"},
            {"label": "域名",   "type": "date_domain"},
            {"label": "备注",   "type": "text"},
        ],
    },
    {
        "id": "tpl_builtin_003",
        "name": "开发平台",
        "is_builtin": True,
        "fields": [
            {"label": "用户名", "type": "text"},
            {"label": "密码",   "type": "secret"},
            {"label": "API Key", "type": "secret"},
            {"label": "备注",   "type": "text"},
        ],
    },
    {
        "id": "tpl_builtin_004",
        "name": "邮箱账号",
        "is_builtin": True,
        "fields": [
            {"label": "用户名",   "type": "text"},
            {"label": "密码",     "type": "secret"},
            {"label": "恢复邮箱", "type": "text"},
            {"label": "备注",     "type": "text"},
        ],
    },
    {
        "id": "tpl_builtin_005",
        "name": "金融/支付",
        "is_builtin": True,
        "fields": [
            {"label": "用户名",   "type": "text"},
            {"label": "密码",     "type": "secret"},
            {"label": "绑定手机", "type": "text"},
            {"label": "密保问题", "type": "secret"},
            {"label": "备注",     "type": "text"},
        ],
    },
]


# ─────────────────────────────────────────────
# 空白 Vault 结构
# ─────────────────────────────────────────────

def create_empty_vault(vault_path: str, account_username: str) -> dict:
    """
    创建一个全新的空白 vault 文件并写入磁盘。

    参数：
        vault_path       - vault 文件的绝对路径（如 .../vaults/sub1.vault）
        account_username - 所属账号名（如 "main"、"sub1"）

    返回：
        新创建的 vault 数据 dict（已写入磁盘）

    调用时机：
        vault_admin.py 创建新账号时调用。
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(vault_path), exist_ok=True)

    data = {
        "version": 2,   # version 2：secret 密文与 entry_id/field_id 绑定（AAD）
        "account": account_username,
        "kdf_params": {
            "algorithm": "pbkdf2",
            "hash": "sha256",
            "iterations": KDF_ITERATIONS,
            "salt": generate_salt(),   # 每个 vault 有独立的 salt
        },
        "categories": [],
        "templates": [copy.deepcopy(t) for t in BUILTIN_TEMPLATES],
        "entries": [],
    }

    _write_json(vault_path, data)
    return data


# ─────────────────────────────────────────────
# 读取 Vault
# ─────────────────────────────────────────────

def load_vault(vault_path: str) -> dict:
    """
    从磁盘读取并解析 vault 文件。

    参数：
        vault_path - vault 文件的绝对路径

    返回：
        解析后的 Python dict

    异常：
        FileNotFoundError - 文件不存在
        VaultFormatError  - JSON 解析失败或版本不支持
    """
    if not os.path.isfile(vault_path):
        raise FileNotFoundError(f"Vault 文件不存在：{vault_path}")

    try:
        with open(vault_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise VaultFormatError(f"Vault 文件 JSON 解析失败：{e}")

    # 版本检查（1 = 无 AAD 旧格式；2 = AAD 绑定格式；升级/降级见 migrate_aad_format）
    version = data.get("version", 0)
    if version not in (1, 2):
        raise VaultFormatError(
            f"不支持的 Vault 文件版本：{version}，当前仅支持版本 1 和 2")

    # 补齐可能缺失的顶层字段（兼容旧版本或手动创建的文件）
    data.setdefault("categories", [])
    data.setdefault("templates", [copy.deepcopy(t) for t in BUILTIN_TEMPLATES])
    data.setdefault("entries", [])

    # 确保内置模板始终存在（防止被意外删除）
    _ensure_builtin_templates(data)

    return data


# ─────────────────────────────────────────────
# 保存 Vault
# ─────────────────────────────────────────────

def file_sha256(path: str) -> str | None:
    """计算文件内容的 SHA-256 哈希；文件不存在或不可读时返回 None。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def backup_file(path: str, suffix: str = ".bak") -> None:
    """
    将现有文件复制为同目录备份（写盘前的滚动上一版保险）。

    手动读写 + fsync，保证 .bak 恒为文件且内容落盘；
    仅当源文件存在时执行；备份失败（权限/磁盘满/.bak 被目录占用）
    静默忽略——备份是尽力而为的保险，不能阻塞正常保存。
    """
    try:
        if os.path.isfile(path):
            with open(path, "rb") as src:
                content = src.read()
            with open(path + suffix, "wb") as dst:
                dst.write(content)
                dst.flush()
                os.fsync(dst.fileno())
    except OSError:
        pass


def save_vault(vault_path: str, data: dict,
               expected_hash: str | None = None) -> None:
    """
    将 vault 数据写入磁盘。

    参数：
        vault_path    - vault 文件的绝对路径
        data          - 要保存的完整 vault dict
        expected_hash - 调用方最后已知的文件内容 SHA-256（加载或上次保存
                        时记录）。提供时若磁盘文件当前内容与之不符，说明
                        文件已被外部程序修改（云盘同步、vault_admin 改密
                        等），此时拒绝写入并抛出 VaultExternallyModifiedError，
                        防止用内存中的旧快照覆盖外部修改（例如改密后用旧
                        密钥的密文覆盖新密钥文件，导致数据无法解密）。

    异常：
        IOError - 写入失败（磁盘满、权限不足等）
        VaultExternallyModifiedError - 文件被外部修改，写入被拒绝

    安全机制：
        替换前将上一版复制为 .bak（滚动单份备份，误删/误改可回退）；
        先写入临时文件，成功后再原子替换原文件，防止写入中断导致数据损坏。
    """
    if expected_hash is not None:
        current_hash = file_sha256(vault_path)
        if current_hash != expected_hash:
            raise VaultExternallyModifiedError(
                "vault 文件已被外部程序修改，为防止覆盖外部修改，"
                "本次写入已取消")

    # 保留上一版备份（在通过外部修改检测之后、替换之前）
    backup_file(vault_path)

    # 先写临时文件
    tmp_path = vault_path + ".tmp"
    try:
        _write_json(tmp_path, data)
        # 原子替换（Windows 上 replace 是原子操作）
        os.replace(tmp_path, vault_path)
    except Exception as e:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise IOError(f"Vault 文件保存失败：{e}")


def save_vault_checked(vault_path: str, data: dict,
                       known_hash: str | None = None) -> str | None:
    """
    带外部修改检测的保存入口（UI 层统一使用）。

    保存前用 known_hash 校验磁盘文件未被外部修改，成功后返回新的
    文件内容哈希——调用方应将其更新为新的已知基准值（如
    session.vault_content_hash），供下次保存校验使用。
    """
    save_vault(vault_path, data, expected_hash=known_hash)
    return file_sha256(vault_path)


def _write_json(path: str, data: dict) -> None:
    """内部：将 dict 写入 JSON 文件（UTF-8，缩进2，保留中文）。

    写入后 flush + fsync，确保 os.replace 原子替换前数据已落盘，
    避免断电时出现"替换完成但内容未写入"的损坏文件。
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())


# ─────────────────────────────────────────────
# 重加密（修改登录密码时调用）
# ─────────────────────────────────────────────

def reencrypt_vault_password(vault_path: str, old_password: str, new_password: str) -> int:
    """
    用新密码重新加密 vault 文件中的所有 ENC: 字段。

    背景：vault 的加密密钥由登录密码 + kdf_params.salt 派生，
    修改登录密码后必须同步重加密，否则所有加密字段都无法解密。

    参数：
        vault_path   - vault 文件的绝对路径
        old_password - 当前登录密码（用于解密现有字段）
        new_password - 新登录密码（用于重新加密）

    返回：
        实际重新加密并保存的字段数量。
        返回 0 的两种情况：
          1. vault 中没有加密字段，无需改动
          2. 字段已经能用新密码解密——说明上次改密在"vault 已重加密、
             密码哈希未更新"时中断，本次调用方只需补更新哈希即可恢复

    异常：
        VaultReencryptError - 字段既无法用旧密码也无法用新密码解密
                              （数据与密码不匹配或已损坏），文件保持原样
        VaultFormatError - version 2 vault 中存在缺 ID 的加密字段
                           （AAD 无法构造），文件保持原样
        VaultFormatError / FileNotFoundError - vault 文件缺失或格式错误

    安全机制：
        两遍式处理：先在内存中把所有字段解密成功，才开始改动并保存；
        任一字段解密失败都不会写盘，避免产生半新半旧的数据。
        重加密保持源 vault version 不变（v1 仍无 AAD、v2 仍带 AAD）——
        升版/降版请显式使用 migrate_aad_format，避免改密时顺带改格式。
    """
    data = load_vault(vault_path)
    kdf_params = data.get("kdf_params", {})
    salt = kdf_params.get("salt", "")
    if not salt:
        raise VaultFormatError("vault 文件缺少 kdf_params.salt，无法重新加密")
    iterations = kdf_params.get("iterations", KDF_ITERATIONS)
    load_hash = file_sha256(vault_path)   # 供保存前检测文件被外部修改

    # 收集所有加密字段（带 entry/field ID，供 AAD 构造）
    encrypted_fields = []
    for entry in data.get("entries", []):
        for field in entry.get("fields", []):
            value = field.get("value", "")
            if isinstance(value, str) and is_encrypted(value):
                encrypted_fields.append((entry, field, value))

    if not encrypted_fields:
        return 0   # 没有加密字段，无需重加密

    # AAD 在 try 之外预先计算：缺 ID 是格式错误（VaultFormatError），
    # 绝不能落进下方自愈 except 被误判为"密码错误"
    try:
        aads = [field_aad(data, entry.get("id"), field.get("id"))
                for entry, field, _ in encrypted_fields]
    except ValueError as e:
        raise VaultFormatError(
            f"version {data.get('version', 1)} 的 vault 存在缺 ID 的加密字段，"
            f"无法构造 AAD 进行重加密：{e}") from e

    old_key = derive_key(old_password, salt, iterations)
    new_key = derive_key(new_password, salt, iterations)

    # 第一遍：全部用旧密码解密（任一失败都不动文件）
    try:
        plaintexts = [decrypt_field(value, old_key, aad=aad)
                      for (_, _, value), aad in zip(encrypted_fields, aads)]
    except (DecryptError, ValueError):
        # 旧密码解不开：可能是上次改密中断，vault 已用新密码加密过
        try:
            plaintexts = [decrypt_field(value, new_key, aad=aad)
                          for (_, _, value), aad in zip(encrypted_fields, aads)]
        except (DecryptError, ValueError) as e:
            raise VaultReencryptError(
                "vault 中的加密字段无法用旧密码或新密码解密，"
                "数据文件与账户密码不匹配或已损坏，未做任何修改"
            ) from e
        return 0   # 已是新密码加密，等待调用方更新密码哈希即可

    # 第二遍：用新密码重新加密并保存（保持源 version 与各自 AAD 语义）
    for (entry, field, _), plaintext, aad in zip(encrypted_fields, plaintexts, aads):
        field["value"] = encrypt_field(plaintext, new_key, aad=aad)

    save_vault(vault_path, data, expected_hash=load_hash)
    return len(encrypted_fields)


# ─────────────────────────────────────────────
# 格式迁移（version 1 ⇄ version 2，登录自动升版 / vault_admin 手动升降版）
# ─────────────────────────────────────────────

def _collect_encrypted_fields(data: dict) -> list:
    """收集所有 ENC: 字段，返回 [(entry_id, field_id, field_dict), ...]。"""
    result = []
    for entry in data.get("entries", []):
        for field in entry.get("fields", []):
            value = field.get("value", "")
            if isinstance(value, str) and is_encrypted(value):
                result.append((entry.get("id"), field.get("id"), field))
    return result


def _aad_for_version(version: int, entry_id, field_id):
    """按给定 version 计算 AAD；version < 2 返回 None，缺 ID 报 VaultFormatError。"""
    if version < 2:
        return None
    try:
        return build_field_aad(entry_id, field_id)
    except ValueError as e:
        raise VaultFormatError(
            f"version {version} 的加密字段缺 ID，无法构造 AAD：{e}") from e


def _migrate_vault_format(vault_path: str, session_key: bytes,
                          target_version: int) -> int:
    """
    内部：把 vault 的全部 ENC 字段在 src/dst AAD 语义间转换并写回。

    幂等：已是目标版本时直接返回 0，不写盘。
    两遍式：全部解密成功才改动内存数据；save_vault 带 expected_hash，
    外部修改（云盘同步）会拒绝写入，文件保持原样。

    返回：实际转换的加密字段数量（0 = 无需转换或本就无加密字段但仍会
          写入 version 变更——仅当 src != dst 时）。
    """
    if target_version not in (1, 2):
        raise ValueError(f"目标版本必须是 1 或 2：{target_version}")

    data = load_vault(vault_path)
    src_version = data.get("version", 1)
    if src_version == target_version:
        return 0   # 幂等：无需迁移

    load_hash = file_sha256(vault_path)
    fields = _collect_encrypted_fields(data)

    # 源/目标 AAD 都在写盘前算好（缺 ID 立即报错，不产生半迁移文件）
    src_aads = [_aad_for_version(src_version, eid, fid)
                for eid, fid, _ in fields]
    dst_aads = [_aad_for_version(target_version, eid, fid)
                for eid, fid, _ in fields]

    # 两遍式：先全部解密成功，再重新加密
    plaintexts = [decrypt_field(field["value"], session_key, aad=aad)
                  for (_, _, field), aad in zip(fields, src_aads)]
    for (_, _, field), plaintext, aad in zip(fields, plaintexts, dst_aads):
        field["value"] = encrypt_field(plaintext, session_key, aad=aad)

    data["version"] = target_version
    save_vault(vault_path, data, expected_hash=load_hash)
    return len(fields)


def migrate_aad_format(vault_path: str, session_key: bytes, *,
                       target_version: int = 2) -> int:
    """
    迁移 vault 的 AAD 格式（version 1 ⇄ 2），用会话密钥直接转换。

    参数：
        vault_path     - vault 文件路径
        session_key    - 已验证的 32 字节会话密钥（登录刚派生的那个，
                         无需再走 PBKDF2）
        target_version - 2 = 升版（登录时自动触发）；1 = 降版
                         （vault_admin 菜单手动触发，供回退旧程序用）

    返回：实际转换的加密字段数量；已是目标版本时返回 0（不写盘）。

    异常：
        VaultFormatError / VaultExternallyModifiedError / DecryptError
        任一异常都不产生半迁移文件（两遍式 + expected_hash 保护）。
    """
    return _migrate_vault_format(vault_path, session_key, target_version)


# ─────────────────────────────────────────────
# 冲突文件检测
# ─────────────────────────────────────────────

def detect_conflict_files(vault_path: str) -> list:
    """
    检测 vault 文件同目录下是否存在云盘冲突副本。

    参数：
        vault_path - 当前 vault 文件的绝对路径

    返回：
        冲突文件名列表（不含路径），空列表表示无冲突

    识别规则：
        云盘冲突副本总是以原文件名开头，后接分隔符（空格/括号/连字符）
        和附加信息，例如：
          test (Casey's conflicted copy 2026-01-01).vault   （Dropbox）
          test-DESKTOP-ABC.vault                            （OneDrive）
          test (来自 xx 的冲突副本 2026-01-01).vault        （坚果云等）
        只认"前缀 + 分隔符"，避免把 test_backup.vault（用户备份）、
        test2.vault（相邻账号名）、contest.vault（仅包含子串）误判为冲突。
    """
    vault_dir = os.path.dirname(vault_path)
    vault_filename = os.path.basename(vault_path)
    base_name = vault_filename.removesuffix(".vault")

    conflict_separators = (" ", "(", "（", "-", "－")

    conflicts = []
    try:
        for fname in os.listdir(vault_dir):
            if fname == vault_filename or not fname.endswith(".vault"):
                continue
            if not fname.startswith(base_name):
                continue
            rest = fname[len(base_name):-len(".vault")]
            if rest and rest.startswith(conflict_separators):
                conflicts.append(fname)
    except OSError:
        pass

    return conflicts


# ─────────────────────────────────────────────
# 分类操作
# ─────────────────────────────────────────────

def add_category(data: dict, name: str) -> dict:
    """
    新增大类。

    参数：
        data - vault dict（会被直接修改）
        name - 大类名称

    返回：
        新创建的大类 dict
    """
    new_cat = {
        "id": generate_id("cat_"),
        "name": name,
        "order": len(data["categories"]),
        "subcategories": [],
    }
    data["categories"].append(new_cat)
    return new_cat


def add_subcategory(data: dict, parent_id: str, name: str) -> dict:
    """
    在指定大类下新增小类。

    参数：
        data      - vault dict（会被直接修改）
        parent_id - 父大类的 id
        name      - 小类名称

    返回：
        新创建的小类 dict，若父类不存在则返回 None
    """
    parent = get_category_by_id(data, parent_id)
    if parent is None:
        return None

    new_sub = {
        "id": generate_id("sub_"),
        "name": name,
        "order": len(parent["subcategories"]),
    }
    parent["subcategories"].append(new_sub)
    return new_sub


def get_category_by_id(data: dict, cat_id: str) -> dict | None:
    """根据 ID 查找大类，返回大类 dict 或 None。"""
    for cat in data.get("categories", []):
        if cat["id"] == cat_id:
            return cat
    return None


def get_subcategory_by_id(data: dict, sub_id: str) -> tuple[dict | None, dict | None]:
    """
    根据小类 ID 查找小类及其父大类。

    返回：
        (父大类 dict, 小类 dict)，若未找到则对应位置为 None
    """
    for cat in data.get("categories", []):
        for sub in cat.get("subcategories", []):
            if sub["id"] == sub_id:
                return cat, sub
    return None, None


def rename_category(data: dict, cat_id: str, new_name: str) -> bool:
    """重命名大类，返回是否成功。"""
    cat = get_category_by_id(data, cat_id)
    if cat:
        cat["name"] = new_name
        return True
    return False


def rename_subcategory(data: dict, sub_id: str, new_name: str) -> bool:
    """重命名小类，返回是否成功。"""
    _, sub = get_subcategory_by_id(data, sub_id)
    if sub:
        sub["name"] = new_name
        return True
    return False


def delete_category(data: dict, cat_id: str) -> int:
    """
    删除大类及其所有小类，受影响的条目移入未分类（category_id 和 subcategory_id 设为 None）。

    返回：
        被移入未分类的条目数量
    """
    cat = get_category_by_id(data, cat_id)
    if cat is None:
        return 0

    # 收集该大类下所有子类 ID
    affected_sub_ids = {sub["id"] for sub in cat.get("subcategories", [])}

    # 移动条目到未分类
    moved = 0
    for entry in data.get("entries", []):
        if entry.get("category_id") == cat_id:
            entry["category_id"] = None
            entry["subcategory_id"] = None
            moved += 1
        elif entry.get("subcategory_id") in affected_sub_ids:
            entry["category_id"] = None
            entry["subcategory_id"] = None
            moved += 1

    # 删除大类
    data["categories"] = [c for c in data["categories"] if c["id"] != cat_id]

    # 重排 order
    for i, cat in enumerate(data["categories"]):
        cat["order"] = i

    return moved


def delete_subcategory(data: dict, sub_id: str) -> int:
    """
    删除小类，受影响的条目移入未分类。

    返回：
        被移入未分类的条目数量
    """
    parent, sub = get_subcategory_by_id(data, sub_id)
    if sub is None:
        return 0

    # 移动条目到未分类
    moved = 0
    for entry in data.get("entries", []):
        if entry.get("subcategory_id") == sub_id:
            entry["subcategory_id"] = None
            moved += 1

    # 删除小类
    parent["subcategories"] = [s for s in parent["subcategories"] if s["id"] != sub_id]

    # 重排 order
    for i, s in enumerate(parent["subcategories"]):
        s["order"] = i

    return moved


def reorder_categories(data: dict, new_order: list) -> None:
    """
    更新大类排序。

    参数：
        data      - vault dict
        new_order - 按新顺序排列的大类 ID 列表

    调用时机：左侧导航栏大类拖拽完成后。

    注意：
        new_order 中遗漏（或无效、重复）的 ID 对应的分类会追加到
        列表末尾，而不是被静默丢弃——调用方传入的顺序不完整时
        不能造成分类数据丢失。
    """
    id_to_cat = {c["id"]: c for c in data["categories"]}
    reordered = []
    seen = set()
    for cat_id in new_order:
        if cat_id in id_to_cat and cat_id not in seen:
            id_to_cat[cat_id]["order"] = len(reordered)
            reordered.append(id_to_cat[cat_id])
            seen.add(cat_id)
    for cat in data["categories"]:
        if cat["id"] not in seen:
            cat["order"] = len(reordered)
            reordered.append(cat)
    data["categories"] = reordered


def reorder_subcategories(data: dict, parent_id: str, new_order: list) -> None:
    """
    更新某大类下的小类排序。

    参数：
        data      - vault dict
        parent_id - 父大类 ID
        new_order - 按新顺序排列的小类 ID 列表

    注意：
        与 reorder_categories 相同，遗漏的 ID 追加到末尾而非丢弃。
    """
    parent = get_category_by_id(data, parent_id)
    if parent is None:
        return
    id_to_sub = {s["id"]: s for s in parent["subcategories"]}
    reordered = []
    seen = set()
    for sub_id in new_order:
        if sub_id in id_to_sub and sub_id not in seen:
            id_to_sub[sub_id]["order"] = len(reordered)
            reordered.append(id_to_sub[sub_id])
            seen.add(sub_id)
    for sub in parent["subcategories"]:
        if sub["id"] not in seen:
            sub["order"] = len(reordered)
            reordered.append(sub)
    parent["subcategories"] = reordered


def move_subcategory(data: dict, sub_id: str, new_parent_id: str) -> bool:
    """
    将小类从当前父大类移动到另一个大类。

    参数：
        data          - vault dict
        sub_id        - 要移动的小类 ID
        new_parent_id - 目标父大类 ID

    返回：
        True 表示移动成功
    """
    old_parent, sub = get_subcategory_by_id(data, sub_id)
    new_parent = get_category_by_id(data, new_parent_id)

    if old_parent is None or sub is None or new_parent is None:
        return False
    if old_parent["id"] == new_parent_id:
        return True  # 没有变化

    # 从原父类移除
    old_parent["subcategories"] = [s for s in old_parent["subcategories"] if s["id"] != sub_id]
    for i, s in enumerate(old_parent["subcategories"]):
        s["order"] = i

    # 添加到新父类末尾
    sub["order"] = len(new_parent["subcategories"])
    new_parent["subcategories"].append(sub)

    # 更新该小类下所有条目的 category_id
    for entry in data.get("entries", []):
        if entry.get("subcategory_id") == sub_id:
            entry["category_id"] = new_parent_id

    return True


# ─────────────────────────────────────────────
# 条目操作
# ─────────────────────────────────────────────

def get_entry_by_id(data: dict, entry_id: str) -> dict | None:
    """根据 ID 查找条目，返回条目 dict 或 None。"""
    for entry in data.get("entries", []):
        if entry["id"] == entry_id:
            return entry
    return None


def add_entry(data: dict, entry: dict) -> dict:
    """
    新增条目到 vault。

    参数：
        data  - vault dict（会被直接修改）
        entry - 条目 dict（应包含所有必要字段，由调用方构建）

    返回：
        添加后的条目 dict
    """
    # 确保有 ID 和时间戳
    if "id" not in entry:
        entry["id"] = generate_id("entry_")
    if "created_at" not in entry:
        entry["created_at"] = now_iso()
    entry["updated_at"] = now_iso()

    # 计算在分类内的排序位置
    if "order" not in entry:
        cat_id = entry.get("category_id")
        same_cat = [e for e in data["entries"] if e.get("category_id") == cat_id]
        max_order = max((e.get("order", 0) for e in same_cat), default=-1)
        entry["order"] = max_order + 1

    data["entries"].append(entry)
    return entry


def update_entry(data: dict, entry_id: str, updated_entry: dict) -> bool:
    """
    更新已有条目。

    参数：
        data          - vault dict（会被直接修改）
        entry_id      - 要更新的条目 ID
        updated_entry - 包含新数据的条目 dict

    返回：
        True 表示更新成功，False 表示未找到条目
    """
    for i, entry in enumerate(data.get("entries", [])):
        if entry["id"] == entry_id:
            updated_entry["id"] = entry_id
            updated_entry["created_at"] = entry.get("created_at", now_iso())
            updated_entry["updated_at"] = now_iso()
            # 保留回收站标记：编辑已删除条目不应使其"复活"
            for k in ("deleted", "deleted_at"):
                if k in entry:
                    updated_entry[k] = entry[k]
            old_cat_id = entry.get("category_id")
            new_cat_id = updated_entry.get("category_id")
            if new_cat_id != old_cat_id:
                same_cat = [e for e in data["entries"]
                            if e.get("category_id") == new_cat_id and e["id"] != entry_id]
                max_order = max((e.get("order", 0) for e in same_cat), default=-1)
                updated_entry["order"] = max_order + 1
            else:
                updated_entry["order"] = entry.get("order", 0)
            data["entries"][i] = updated_entry
            return True
    return False


def delete_entry(data: dict, entry_id: str) -> bool:
    """
    将条目移入回收站（软删除：打标记，不丢数据）。

    已删除条目不会出现在条目列表、搜索、到期扫描和导出中，
    可用 restore_entry 恢复，或用 purge_entry 永久删除。
    注意：重加密（改密）仍会处理已删除条目的加密字段，
    否则它们将永久无法解密。

    返回：
        True 表示标记成功，False 表示未找到
    """
    entry = get_entry_by_id(data, entry_id)
    if entry is None:
        return False
    entry["deleted"] = True
    entry["deleted_at"] = now_iso()
    return True


def restore_entry(data: dict, entry_id: str) -> bool:
    """从回收站恢复条目。返回是否成功。"""
    entry = get_entry_by_id(data, entry_id)
    if entry is None or not entry.get("deleted"):
        return False
    entry["deleted"] = False
    entry.pop("deleted_at", None)
    return True


def purge_entry(data: dict, entry_id: str) -> bool:
    """
    从回收站永久删除条目（不可恢复）。

    返回：
        True 表示删除成功，False 表示未找到
    """
    original_len = len(data.get("entries", []))
    data["entries"] = [e for e in data["entries"] if e["id"] != entry_id]
    return len(data["entries"]) < original_len


def get_deleted_entries(data: dict) -> list:
    """返回回收站中的条目（按删除时间降序，最新删除的在最前）。"""
    deleted = [e for e in data.get("entries", []) if e.get("deleted")]
    return sorted(deleted, key=lambda e: e.get("deleted_at", ""),
                  reverse=True)


def count_active_entries(data: dict) -> int:
    """返回未删除（活跃）条目数量，用于状态栏计数。"""
    return len([e for e in data.get("entries", []) if not e.get("deleted")])


def reorder_entries(data: dict, category_id: str | None, new_order: list) -> None:
    """
    更新某分类内的条目排序。

    参数：
        data        - vault dict
        category_id - 大类 ID（None 表示未分类）
        new_order   - 按新顺序排列的条目 ID 列表
    """
    id_to_order = {eid: i for i, eid in enumerate(new_order)}
    for entry in data.get("entries", []):
        if entry.get("category_id") == category_id and entry["id"] in id_to_order:
            entry["order"] = id_to_order[entry["id"]]


def get_entries_by_category(data: dict, category_id: str | None,
                             subcategory_id: str | None = ...) -> list:
    """
    按分类筛选条目。

    参数：
        data           - vault dict
        category_id    - 大类 ID；None 表示未分类；"__all__" 表示全部
        subcategory_id - 小类 ID；None 表示该大类所有条目（不限小类）
                         Ellipsis（默认）表示不限小类

    返回：
        按 order 排序的条目列表（浅拷贝引用）。
        回收站条目（deleted 标记）不包含在内——查看回收站请用
        get_deleted_entries()。
    """
    entries = [e for e in data.get("entries", []) if not e.get("deleted")]

    if category_id == "__all__":
        result = list(entries)
    elif category_id is None:
        # 未分类
        result = [e for e in entries if e.get("category_id") is None]
    else:
        result = [e for e in entries if e.get("category_id") == category_id]
        if subcategory_id is not ...:
            result = [e for e in result if e.get("subcategory_id") == subcategory_id]

    return sorted(result, key=lambda e: e.get("order", 0))


def find_first_encrypted_field(data: dict) -> tuple | None:
    """
    返回 vault 中第一个 ENC: 加密字段的 (entry_id, field_id, value)，
    用于登录时校验密钥——version 2 解密需要 entry/field ID 构造 AAD。

    参数：
        data - vault dict

    返回：
        (entry_id, field_id, value) 三元组；没有加密字段时返回 None。
        回收站条目的字段不参与登录校验。
        entry_id/field_id 取自文件内容，可能为 None（畸形旧文件），
        由调用方在构造 AAD 时按 version 决定是否报错。
    """
    for entry in data.get("entries", []):
        if entry.get("deleted"):
            continue
        for field in entry.get("fields", []):
            value = field.get("value", "")
            if isinstance(value, str) and is_encrypted(value):
                return (entry.get("id"), field.get("id"), value)
    return None


def find_first_encrypted_value(data: dict) -> str | None:
    """
    兼容包装：只返回第一个 ENC: 字段的值（旧调用点，如 _test_p4）。
    version 2 vault 的密钥校验解密请改用 find_first_encrypted_field
    取三元组后构造 AAD。
    """
    hit = find_first_encrypted_field(data)
    return hit[2] if hit else None


# ─────────────────────────────────────────────
# 到期提醒扫描
# ─────────────────────────────────────────────

def scan_expiry(data: dict) -> list:
    """
    扫描所有条目的 date 和 date_domain 类型字段，返回到期信息列表。

    返回：
        列表，每项是 dict：
        {
            "entry_id":   str,   # 条目 ID
            "entry_name": str,   # 条目名称
            "field_label": str,  # 字段名称（如"域名1"）
            "domain":     str,   # 域名（date_domain 类型）或 ""
            "expire_date": str,  # 到期日期字符串 YYYY-MM-DD
            "days_left":  int,   # 距今天数（负数表示已过期）
            "level":      str,   # "red" / "yellow" / "green"
        }
        按 days_left 升序排列（最紧急的在最前）
    """
    today = date.today()
    results = []

    for entry in data.get("entries", []):
        if entry.get("deleted"):
            continue   # 回收站条目不参与到期提醒
        entry_id = entry["id"]
        entry_name = entry.get("name", "（未命名）")

        for field in entry.get("fields", []):
            field_type = field.get("type")
            field_label = field.get("label", "")
            field_value = field.get("value", "")

            if not field_value:
                continue

            expire_str = None
            domain = ""

            if field_type == "date":
                expire_str = field_value.strip()

            elif field_type == "date_domain":
                # 格式："域名名称|YYYY-MM-DD"
                parts = field_value.split("|", 1)
                if len(parts) == 2:
                    domain = parts[0].strip()
                    expire_str = parts[1].strip()

            if expire_str is None:
                continue

            try:
                expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
            except ValueError:
                continue  # 日期格式错误，跳过

            days_left = (expire_date - today).days

            if days_left <= 30:
                level = "red"
            elif days_left <= 90:
                level = "yellow"
            else:
                level = "green"

            results.append({
                "entry_id":    entry_id,
                "entry_name":  entry_name,
                "field_label": field_label,
                "domain":      domain,
                "expire_date": expire_str,
                "days_left":   days_left,
                "level":       level,
            })

    results.sort(key=lambda x: x["days_left"])
    return results


def get_expiry_level(expiry_list: list) -> str:
    """
    根据到期列表返回整体告警级别。

    返回：
        "red"    - 有任意一项 <= 30 天
        "yellow" - 有任意一项 <= 90 天（无红色）
        "green"  - 全部 > 90 天或无到期字段
    """
    if not expiry_list:
        return "green"
    levels = {item["level"] for item in expiry_list}
    if "red" in levels:
        return "red"
    if "yellow" in levels:
        return "yellow"
    return "green"


# ─────────────────────────────────────────────
# 搜索
# ─────────────────────────────────────────────

def search_entries(data: dict, query: str) -> list:
    """
    在所有条目中全文搜索（仅搜索明文字段）。

    搜索范围：
        条目名称、URL、标签、分类名称、
        text 字段的 label 和 value、
        date 字段的 label、
        date_domain 字段的 label 和域名部分、
        secret 字段仅搜索 label（不搜索加密值！）

    参数：
        data  - vault dict
        query - 搜索词，支持空格分隔多关键词（AND 逻辑）

    返回：
        匹配的条目列表，按原 order 排序
    """
    query = query.strip()
    if not query:
        return get_entries_by_category(data, "__all__")

    keywords = query.lower().split()

    # 构建分类名称查找表
    cat_names = {}
    sub_names = {}
    for cat in data.get("categories", []):
        cat_names[cat["id"]] = cat["name"]
        for sub in cat.get("subcategories", []):
            sub_names[sub["id"]] = sub["name"]

    results = []
    for entry in data.get("entries", []):
        if entry.get("deleted"):
            continue   # 回收站条目不参与搜索
        searchable_parts = []

        # 条目基础字段
        searchable_parts.append(entry.get("name", ""))
        searchable_parts.append(entry.get("url", ""))
        searchable_parts.extend(entry.get("tags", []))

        # 分类名称
        cat_id = entry.get("category_id")
        sub_id = entry.get("subcategory_id")
        if cat_id and cat_id in cat_names:
            searchable_parts.append(cat_names[cat_id])
        if sub_id and sub_id in sub_names:
            searchable_parts.append(sub_names[sub_id])

        # 字段内容
        for field in entry.get("fields", []):
            field_type = field.get("type", "text")
            label = field.get("label", "")
            value = field.get("value", "")

            searchable_parts.append(label)  # 所有类型都搜索 label

            if field_type == "text":
                searchable_parts.append(value)
            elif field_type == "date_domain":
                # 只搜索域名部分（| 前）
                domain_part = value.split("|")[0].strip() if "|" in value else value
                searchable_parts.append(domain_part)
            # secret 和 date 类型不搜索 value

        # 合并搜索文本，全部转小写
        search_text = " ".join(searchable_parts).lower()

        # 所有关键词都匹配才包含（AND 逻辑）
        if all(kw in search_text for kw in keywords):
            results.append(entry)

    return sorted(results, key=lambda e: e.get("order", 0))


# ─────────────────────────────────────────────
# 模板操作
# ─────────────────────────────────────────────

def get_template_by_id(data: dict, tpl_id: str) -> dict | None:
    """根据 ID 查找模板，返回模板 dict 或 None。"""
    for tpl in data.get("templates", []):
        if tpl["id"] == tpl_id:
            return tpl
    return None


def add_custom_template(data: dict, name: str, fields: list) -> dict:
    """
    新增自定义模板。

    参数：
        data   - vault dict
        name   - 模板名称
        fields - 字段定义列表，每项 {"label": str, "type": str}

    返回：
        新创建的模板 dict
    """
    new_tpl = {
        "id": generate_id("tpl_custom_"),
        "name": name,
        "is_builtin": False,
        "fields": fields,
    }
    data["templates"].append(new_tpl)
    return new_tpl


def update_template(data: dict, tpl_id: str, name: str = None, fields: list = None) -> bool:
    """
    更新模板（内置模板只允许改 fields，不允许改 name；自定义模板可全改）。

    返回：
        True 表示更新成功
    """
    tpl = get_template_by_id(data, tpl_id)
    if tpl is None:
        return False
    if name is not None and not tpl.get("is_builtin"):
        tpl["name"] = name
    if fields is not None:
        tpl["fields"] = fields
    return True


def delete_custom_template(data: dict, tpl_id: str) -> bool:
    """
    删除自定义模板（内置模板不可删除）。

    返回：
        True 表示删除成功，False 表示未找到或是内置模板
    """
    tpl = get_template_by_id(data, tpl_id)
    if tpl is None or tpl.get("is_builtin"):
        return False
    data["templates"] = [t for t in data["templates"] if t["id"] != tpl_id]
    return True


def build_entry_from_template(tpl_id: str, data: dict) -> dict:
    """
    根据模板构建一个空白条目 dict（用于新建条目时预填字段结构）。

    返回：
        空白条目 dict，name 为空，fields 按模板结构创建但 value 为空字符串
    """
    tpl = get_template_by_id(data, tpl_id)
    fields = tpl["fields"] if tpl else []

    entry_fields = []
    for i, f in enumerate(fields):
        entry_fields.append({
            "id":    f"fld_{i+1:03d}",
            "label": f["label"],
            "type":  f["type"],
            "value": "",
            "order": i,
        })

    return {
        "id":             generate_id("entry_"),
        "name":           "",
        "category_id":    None,
        "subcategory_id": None,
        "url":            "",
        "tags":           [],
        "order":          0,
        "created_at":     now_iso(),
        "updated_at":     now_iso(),
        "fields":         entry_fields,
    }


# ─────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────

def _ensure_builtin_templates(data: dict) -> None:
    """确保所有内置模板都存在于 vault 的 templates 列表中（幂等操作）。"""
    existing_ids = {t["id"] for t in data.get("templates", [])}
    for builtin in BUILTIN_TEMPLATES:
        if builtin["id"] not in existing_ids:
            data["templates"].append(copy.deepcopy(builtin))


# ─────────────────────────────────────────────
# 自定义异常
# ─────────────────────────────────────────────

class VaultFormatError(Exception):
    """Vault 文件格式错误或版本不支持。"""
    pass


class VaultReencryptError(Exception):
    """vault 重加密失败：加密字段与提供的密码不匹配或数据已损坏。"""
    pass


class VaultExternallyModifiedError(Exception):
    """vault 文件在加载后被外部程序修改（云盘同步 / vault_admin 等），保存被拒绝。"""
    pass


# ─────────────────────────────────────────────
# 模块自测
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import os

    print("=== TJKEY vault_io.py 自测 ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "vaults", "test.vault")
        os.makedirs(os.path.dirname(vault_path), exist_ok=True)

        # 1. 创建空白 vault
        data = create_empty_vault(vault_path, "test_user")
        print(f"[1] 创建 vault: {vault_path}")
        print(f"    版本: {data['version']}, 账号: {data['account']}")
        print(f"    内置模板数: {len(data['templates'])}")
        assert len(data["templates"]) == 5, "应有5个内置模板"
        assert data["version"] == 2, "新建 vault 应为 version 2（AAD 格式）"
        print("    [OK] 空白 vault 创建正常（version 2）")

        # 2. 读取 vault
        loaded = load_vault(vault_path)
        assert loaded["account"] == "test_user"
        print("[2] [OK] Vault 读取正常")

        # 3. 添加分类
        cat = add_category(data, "域名注册")
        sub = add_subcategory(data, cat["id"], "Cloudflare")
        print(f"[3] 添加分类: {cat['name']} > {sub['name']}")
        print("    [OK] 分类操作正常")

        # 4. 从模板创建条目
        entry = build_entry_from_template("tpl_builtin_002", data)
        entry["name"] = "Cloudflare 主号"
        entry["category_id"] = cat["id"]
        entry["subcategory_id"] = sub["id"]
        entry["fields"][0]["value"] = "admin@gmail.com"
        entry["fields"][1]["value"] = "ENC:fake_encrypted_value"
        entry["fields"][2]["value"] = "example.com|2026-06-01"
        add_entry(data, entry)
        print(f"[4] 添加条目: {entry['name']}, 字段数: {len(entry['fields'])}")
        print("    [OK] 条目添加正常")

        # 5. 搜索
        save_vault(vault_path, data)
        results = search_entries(data, "cloudflare")
        assert len(results) == 1
        results2 = search_entries(data, "admin gmail")
        assert len(results2) == 1
        results3 = search_entries(data, "notexist")
        assert len(results3) == 0
        print("[5] [OK] 搜索功能正常")

        # 6. 到期扫描
        expiry = scan_expiry(data)
        assert len(expiry) == 1
        print(f"[6] 到期扫描: {expiry[0]['entry_name']} | {expiry[0]['domain']} | 剩余 {expiry[0]['days_left']} 天 | {expiry[0]['level']}")
        level = get_expiry_level(expiry)
        print(f"    整体告警级别: {level}")
        print("    [OK] 到期扫描正常")

        # 7. 冲突文件检测（前缀+分隔符规则，正反用例）
        vp_dir = os.path.dirname(vault_path)
        open(os.path.join(vp_dir, "test (冲突副本 2026-01-01).vault"), "w").close()
        open(os.path.join(vp_dir, "test-DESKTOP-ABC.vault"), "w").close()   # OneDrive 风格
        open(os.path.join(vp_dir, "test_backup.vault"), "w").close()        # 用户备份，不应误报
        open(os.path.join(vp_dir, "test2.vault"), "w").close()              # 相邻账号名，不应误报
        open(os.path.join(vp_dir, "contest.vault"), "w").close()            # 仅含子串，不应误报
        conflicts = detect_conflict_files(vault_path)
        assert len(conflicts) == 2, f"应恰好检出 2 个冲突副本: {conflicts}"
        print(f"[7] 检测到冲突文件: {conflicts}")
        print("    [OK] 冲突检测正常（无误报）")

        # 8. 删除分类（条目移入未分类）
        moved = delete_category(data, cat["id"])
        assert moved == 1
        uncategorized = get_entries_by_category(data, None)
        assert len(uncategorized) == 1
        print(f"[8] 删除分类，{moved} 个条目移入未分类")
        print("    [OK] 分类删除正常")

        # 9. 软删除（回收站）：列表/搜索/到期扫描不再包含，可恢复或永久删除
        deleted = delete_entry(data, entry["id"])
        assert deleted
        assert len(data["entries"]) == 1, "软删除不应移除条目数据"
        assert len(get_entries_by_category(data, "__all__")) == 0, \
            "活跃列表不应包含回收站条目"
        assert len(search_entries(data, "cloudflare")) == 0, \
            "搜索不应命中回收站条目"
        assert scan_expiry(data) == [], "到期扫描不应包含回收站条目"
        trash = get_deleted_entries(data)
        assert len(trash) == 1 and trash[0]["id"] == entry["id"]
        # 恢复
        assert restore_entry(data, entry["id"])
        assert len(get_entries_by_category(data, "__all__")) == 1
        assert get_deleted_entries(data) == []
        # 再次软删除后永久删除
        delete_entry(data, entry["id"])
        assert purge_entry(data, entry["id"])
        assert len(data["entries"]) == 0
        print("[9] [OK] 条目软删除/恢复/永久删除正常")

        # 10. 自定义模板
        custom_tpl = add_custom_template(data, "我的模板", [
            {"label": "账号", "type": "text"},
            {"label": "密码", "type": "secret"},
        ])
        assert not custom_tpl["is_builtin"]
        ok = delete_custom_template(data, custom_tpl["id"])
        assert ok
        # 内置模板不可删除
        not_ok = delete_custom_template(data, "tpl_builtin_001")
        assert not not_ok
        print("[10] [OK] 自定义模板增删正常")

        # 11. 重加密（修改登录密码时的核心操作）
        from crypto import (derive_key, encrypt_field, decrypt_field,
                            DecryptError, build_field_aad)
        key_a = derive_key("password_a", data["kdf_params"]["salt"])
        key_b = derive_key("password_b", data["kdf_params"]["salt"])
        reenc_aad = build_field_aad("entry_reenc", "fld_001")
        data["entries"].append({
            "id": "entry_reenc", "name": "重加密测试",
            "category_id": None, "subcategory_id": None, "order": 0,
            "fields": [{"id": "fld_001", "label": "密码", "type": "secret",
                        "value": encrypt_field("重加密测试", key_a,
                                               aad=reenc_aad), "order": 0}],
        })
        save_vault(vault_path, data)
        n = reencrypt_vault_password(vault_path, "password_a", "password_b")
        assert n == 1
        loaded = load_vault(vault_path)
        assert loaded["version"] == 2, "重加密不应改变 version（不顺带升版）"
        new_val = loaded["entries"][0]["fields"][0]["value"]
        assert decrypt_field(new_val, key_b, aad=reenc_aad) == "重加密测试"
        try:
            decrypt_field(new_val, key_a, aad=reenc_aad)
            print("    [FAIL] 旧密码不应能解密新数据！")
        except DecryptError:
            pass
        print("[11] [OK] vault 重加密正常（保持 version 2 + AAD）")

        # 12. 查找第一个加密字段（登录时密钥校验用）
        assert find_first_encrypted_value(loaded) == new_val
        assert find_first_encrypted_value({"entries": []}) is None
        hit = find_first_encrypted_field(loaded)
        assert hit == ("entry_reenc", "fld_001", new_val)
        print("[12] [OK] 查找加密字段正常（value 包装 + 三元组）")

        # 13. 格式迁移 v2 ⇄ v1：AAD 语义随 version 转换，幂等不重写
        mkey = key_b   # 同一密码+salt，复用已有派生结果
        hash_before = file_sha256(vault_path)
        assert migrate_aad_format(vault_path, mkey, target_version=2) == 0, \
            "已是 v2 应幂等返回 0"
        assert file_sha256(vault_path) == hash_before, "幂等迁移不应写盘"

        n_down = migrate_aad_format(vault_path, mkey, target_version=1)
        assert n_down == 1
        down = load_vault(vault_path)
        assert down["version"] == 1
        down_val = down["entries"][0]["fields"][0]["value"]
        assert decrypt_field(down_val, mkey) == "重加密测试", \
            "v1 密文应无 AAD 可解"
        try:
            decrypt_field(down_val, mkey, aad=reenc_aad)
            raise AssertionError("v1 密文带 AAD 解密应失败")
        except DecryptError:
            pass

        n_up = migrate_aad_format(vault_path, mkey, target_version=2)
        assert n_up == 1
        up = load_vault(vault_path)
        assert up["version"] == 2
        up_val = up["entries"][0]["fields"][0]["value"]
        assert decrypt_field(up_val, mkey, aad=reenc_aad) == "重加密测试"
        print("[13] [OK] migrate v2⇄v1 双向转换 + 幂等不写盘")

        # 14. version 2 缺 ID 防呆：AAD 构造失败，迁移/重加密前即报错
        bad = load_vault(vault_path)
        bad["entries"][0]["fields"][0].pop("id")
        save_vault(vault_path, bad)
        try:
            migrate_aad_format(vault_path, mkey, target_version=1)
            raise AssertionError("v2 缺 field id 应报 VaultFormatError")
        except VaultFormatError:
            pass
        try:
            reencrypt_vault_password(vault_path, "password_b", "password_c")
            raise AssertionError("v2 缺 field id 重加密应报 VaultFormatError")
        except VaultFormatError:
            pass
        assert load_vault(vault_path)["version"] == 2, "报错后文件应保持原样"
        print("[14] [OK] v2 缺 ID 防呆：迁移/重加密均拒绝，文件不被破坏")

    print("\n=== 全部测试通过 [OK] ===")
