# accounts.py
# TJKEY 账户配置模块
#
# 负责 accounts.conf 和 app.conf 的读写，以及账户验证逻辑。
# 所有密码以哈希形式存储，永远不存明文。

import json
import os
import copy
from typing import Optional

from crypto import hash_password, verify_password, now_iso
from vault_io import reencrypt_vault_password, backup_file


# ─────────────────────────────────────────────
# 文件路径工具
# ─────────────────────────────────────────────

def get_accounts_path(myVault_path: str) -> str:
    """返回 accounts.conf 的绝对路径。"""
    return os.path.join(myVault_path, "accounts.conf")


def get_app_conf_path(myVault_path: str) -> str:
    """返回 app.conf 的绝对路径。"""
    return os.path.join(myVault_path, "app.conf")


def get_app_config_path(app_dir: str) -> str:
    """
    返回程序目录下 app.config 的绝对路径。
    app.config 存储 MyVault 文件夹路径，与 app.conf 不同：
      - app.config：在 VaultApp 程序目录，记录数据文件夹位置
      - app.conf：在 MyVault 数据文件夹，记录用户偏好
    """
    return os.path.join(app_dir, "app.config")


# ─────────────────────────────────────────────
# app.config 操作（程序目录，记录 MyVault 路径）
# ─────────────────────────────────────────────

def read_app_config(app_dir: str) -> str:
    """
    读取程序目录下的 app.config，返回 MyVault 文件夹的绝对路径。

    返回：
        路径字符串，若文件不存在或为空则返回 ""
    """
    config_path = get_app_config_path(app_dir)
    if not os.path.isfile(config_path):
        return ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def write_app_config(app_dir: str, myVault_path: str) -> None:
    """
    将 MyVault 文件夹路径写入程序目录下的 app.config。

    参数：
        app_dir      - VaultApp 程序目录的绝对路径
        myVault_path - MyVault 数据文件夹的绝对路径
    """
    config_path = get_app_config_path(app_dir)
    tmp_path = config_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(myVault_path.strip())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, config_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise IOError(f"app.config 保存失败：{e}") from e


# ─────────────────────────────────────────────
# app.conf 操作（MyVault 目录，记录用户偏好）
# ─────────────────────────────────────────────

DEFAULT_APP_CONF = {
    "theme": "dark",
    "auto_lock_minutes": 2,
    "last_account": "",
    "window_geometry": {
        "width": 1100,
        "height": 720,
        "x": 100,
        "y": 100,
    },
}


def load_app_conf(myVault_path: str) -> dict:
    """
    读取 app.conf，返回用户偏好配置 dict。
    若文件不存在，返回默认配置。
    """
    conf_path = get_app_conf_path(myVault_path)
    if not os.path.isfile(conf_path):
        # 必须深拷贝：浅拷贝下嵌套的 window_geometry 与模块常量共享，
        # 调用方一旦原地修改会污染后续所有"默认配置"
        return copy.deepcopy(DEFAULT_APP_CONF)

    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        # 补齐缺失字段
        result = copy.deepcopy(DEFAULT_APP_CONF)
        result.update(loaded)
        return result
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(DEFAULT_APP_CONF)


def save_app_conf(myVault_path: str, conf: dict) -> None:
    """
    保存用户偏好配置到 app.conf（临时文件 + 原子替换，防止断电写坏）。

    异常：
        ValueError  - myVault_path 为空（os.path.join("", "app.conf") 是
                      相对路径，会把 app.conf 误写到进程 cwd）
        IOError     - 写入失败
    """
    if not myVault_path:
        raise ValueError("myVault_path 不能为空，拒绝把 app.conf 写到相对路径")
    conf_path = get_app_conf_path(myVault_path)
    tmp_path = conf_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, conf_path)
    except OSError as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise IOError(f"无法保存 app.conf：{e}") from e


def update_app_conf(myVault_path: str, **kwargs) -> dict:
    """
    更新 app.conf 中的指定字段并保存。

    用法示例：
        update_app_conf(vault_path, theme="light", auto_lock_minutes=5)

    异常：
        ValueError - myVault_path 为空（见 save_app_conf）

    返回：
        更新后的完整 conf dict
    """
    if not myVault_path:
        raise ValueError("myVault_path 不能为空，拒绝把 app.conf 写到相对路径")
    conf = load_app_conf(myVault_path)
    conf.update(kwargs)
    save_app_conf(myVault_path, conf)
    return conf


# ─────────────────────────────────────────────
# accounts.conf 读写
# ─────────────────────────────────────────────

def load_accounts(myVault_path: str) -> dict:
    """
    读取 accounts.conf，返回账户配置 dict。

    异常：
        FileNotFoundError  - accounts.conf 不存在
        AccountsFormatError - JSON 解析失败
    """
    path = get_accounts_path(myVault_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"accounts.conf 不存在：{path}\n请先运行 vault_admin.py 创建账号。")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise AccountsFormatError(f"accounts.conf 格式错误：{e}")

    data.setdefault("default_account", "")
    data.setdefault("accounts", [])
    return data


def save_accounts(myVault_path: str, data: dict) -> None:
    """将账户配置写入 accounts.conf。

    accounts.conf 存有全部账号的密码哈希，损坏即所有账号失联；
    替换前滚动备份上一版为 accounts.conf.bak。
    """
    path = get_accounts_path(myVault_path)
    # 保留上一版备份
    backup_file(path)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise IOError(f"accounts.conf 保存失败：{e}")


# ─────────────────────────────────────────────
# 账户查询
# ─────────────────────────────────────────────

def get_account(accounts_data: dict, username: str) -> Optional[dict]:
    """
    根据用户名查找账户配置。

    返回：
        账户 dict 或 None（若不存在）
    """
    for acc in accounts_data.get("accounts", []):
        if acc.get("username") == username:
            return acc
    return None


def list_usernames(accounts_data: dict) -> list:
    """返回所有账号的用户名列表。"""
    return [acc["username"] for acc in accounts_data.get("accounts", [])]


def get_default_username(accounts_data: dict) -> str:
    """返回默认账号名（登录界面预填）。"""
    return accounts_data.get("default_account", "")


def get_vault_path(myVault_path: str, accounts_data: dict, username: str) -> str:
    """
    根据用户名获取对应 vault 文件的绝对路径。

    返回：
        绝对路径字符串，或 "" 若账号不存在或路径非法

    安全：
        accounts.conf 会被云盘同步，vault_file 可能被截断或篡改；
        解析出的路径若指向 MyVault 目录之外（如包含 ".."），一律拒绝。
    """
    acc = get_account(accounts_data, username)
    if acc is None:
        return ""
    relative = acc.get("vault_file", "")
    if not relative:
        return ""

    base = os.path.abspath(myVault_path)
    full = os.path.abspath(os.path.join(base, relative))
    try:
        if os.path.commonpath([base, full]) != base:
            return ""   # 指向 MyVault 之外，拒绝（跨盘符时 commonpath 抛 ValueError）
    except ValueError:
        return ""
    return full


# ─────────────────────────────────────────────
# 账户验证
# ─────────────────────────────────────────────

def verify_login(accounts_data: dict, username: str, password: str) -> bool:
    """
    验证登录密码是否正确。

    参数：
        accounts_data - load_accounts() 返回的 dict
        username      - 账号名
        password      - 用户输入的登录密码（明文）

    返回：
        True  - 验证通过
        False - 账号不存在或密码错误
    """
    acc = get_account(accounts_data, username)
    if acc is None:
        return False
    pwd_hash = acc.get("password_hash", "")
    if not pwd_hash:
        return False
    return verify_password(password, pwd_hash)


def verify_export_password(accounts_data: dict, username: str, export_password: str) -> bool:
    """
    验证导出密码是否正确。

    参数：
        export_password - 用户输入的二级导出密码（明文）

    返回：
        True / False
    """
    acc = get_account(accounts_data, username)
    if acc is None:
        return False
    export_hash = acc.get("export_password_hash", "")
    if not export_hash:
        return False
    return verify_password(export_password, export_hash)


# ─────────────────────────────────────────────
# 账户创建（供 vault_admin.py 调用）
# ─────────────────────────────────────────────

def create_account(myVault_path: str, username: str, display_name: str,
                   password: str, export_password: str) -> dict:
    """
    创建新账号并写入 accounts.conf。

    参数：
        myVault_path   - MyVault 文件夹路径
        username       - 账号标识符（字母数字下划线）
        display_name   - 显示名称（如 "大号"）
        password       - 登录密码（明文，将被哈希后存储）
        export_password - 导出密码（明文，将被哈希后存储）

    返回：
        新账号的 dict

    异常：
        ValueError          - username 格式不合法或已存在
        AccountsFormatError - accounts.conf 格式错误
    """
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        raise ValueError(f"用户名 '{username}' 格式不合法，只允许字母、数字和下划线")

    # 读取或初始化 accounts.conf
    accounts_path = get_accounts_path(myVault_path)
    if os.path.isfile(accounts_path):
        accounts_data = load_accounts(myVault_path)
    else:
        accounts_data = {"default_account": "", "accounts": []}

    # 检查 username 唯一性
    if get_account(accounts_data, username) is not None:
        raise ValueError(f"账号 '{username}' 已存在")

    vault_relative = f"vaults/{username}.vault"
    now = now_iso()

    new_account = {
        "username":            username,
        "display_name":        display_name,
        "vault_file":          vault_relative,
        "password_hash":       hash_password(password),
        "export_password_hash": hash_password(export_password),
        "created_at":          now,
        "updated_at":          now,
    }

    accounts_data["accounts"].append(new_account)

    # 首个账号自动设为默认
    if not accounts_data["default_account"]:
        accounts_data["default_account"] = username

    save_accounts(myVault_path, accounts_data)
    return new_account


def change_password(myVault_path: str, username: str,
                    old_password: str, new_password: str) -> bool:
    """
    修改登录密码。需要验证旧密码。
    同时用新密码重新加密该账号的 vault 文件——加密密钥由登录密码派生，
    只更新哈希不重加密会导致所有加密字段永久无法解密。

    执行顺序：先重加密 vault，再更新密码哈希。
    若在中途中断（如断电），重试同一命令即可自动恢复：
    vault 已是新密码加密时会跳过重加密，仅补更新哈希。

    返回：
        True  - 修改成功
        False - 旧密码错误或账号不存在

    异常：
        VaultReencryptError - vault 字段与密码不匹配或已损坏（未做任何修改）
        VaultFormatError    - vault 文件格式错误（未做任何修改）
    """
    accounts_data = load_accounts(myVault_path)
    if not verify_login(accounts_data, username, old_password):
        return False

    acc = get_account(accounts_data, username)
    if acc is None:
        return False

    # 用新密码重新加密 vault（账号尚无 vault 文件时跳过）
    vault_path = get_vault_path(myVault_path, accounts_data, username)
    if vault_path and os.path.isfile(vault_path):
        reencrypt_vault_password(vault_path, old_password, new_password)

    acc["password_hash"] = hash_password(new_password)
    acc["updated_at"] = now_iso()
    save_accounts(myVault_path, accounts_data)
    return True


def change_export_password(myVault_path: str, username: str,
                           old_export_password: str, new_export_password: str) -> bool:
    """
    修改导出密码。需要验证旧导出密码。

    返回：
        True  - 修改成功
        False - 旧密码错误或账号不存在
    """
    accounts_data = load_accounts(myVault_path)
    if not verify_export_password(accounts_data, username, old_export_password):
        return False

    acc = get_account(accounts_data, username)
    acc["export_password_hash"] = hash_password(new_export_password)
    acc["updated_at"] = now_iso()
    save_accounts(myVault_path, accounts_data)
    return True


def delete_account(myVault_path: str, username: str, password: str) -> bool:
    """
    删除账号（需验证登录密码）并删除对应 vault 文件。

    返回：
        True  - 删除成功
        False - 密码错误或账号不存在

    注意：
        此操作不可逆，vault 文件将被永久删除。
    """
    accounts_data = load_accounts(myVault_path)
    if not verify_login(accounts_data, username, password):
        return False

    acc = get_account(accounts_data, username)
    if acc is None:
        return False

    # 先取路径（账号还在列表中时才能解析），再更新配置，最后删文件：
    # 若顺序相反（先删文件后写配置），写入失败会留下"账号在、数据无"的
    # 不可恢复状态；反过来失败最多残留一个孤儿 vault 文件，数据仍可恢复
    vault_path = get_vault_path(myVault_path, accounts_data, username)

    # 从列表中移除
    accounts_data["accounts"] = [
        a for a in accounts_data["accounts"] if a["username"] != username
    ]

    # 若删除的是默认账号，重新设置默认
    if accounts_data["default_account"] == username:
        remaining = accounts_data["accounts"]
        accounts_data["default_account"] = remaining[0]["username"] if remaining else ""

    save_accounts(myVault_path, accounts_data)

    # 配置已更新，删除 vault 文件
    if vault_path and os.path.isfile(vault_path):
        try:
            os.remove(vault_path)
        except OSError as e:
            raise IOError(
                f"账号已从配置中移除，但数据文件删除失败：{e}\n"
                f"请手动删除：{vault_path}"
            ) from e

    return True


def set_default_account(myVault_path: str, username: str) -> bool:
    """
    设置默认登录账号。

    返回：
        True  - 设置成功
        False - 账号不存在
    """
    accounts_data = load_accounts(myVault_path)
    if get_account(accounts_data, username) is None:
        return False
    accounts_data["default_account"] = username
    save_accounts(myVault_path, accounts_data)
    return True


def update_display_name(myVault_path: str, username: str, new_display_name: str) -> bool:
    """
    修改账号显示名称。

    返回：
        True  - 修改成功
        False - 账号不存在
    """
    accounts_data = load_accounts(myVault_path)
    acc = get_account(accounts_data, username)
    if acc is None:
        return False
    acc["display_name"] = new_display_name
    acc["updated_at"] = now_iso()
    save_accounts(myVault_path, accounts_data)
    return True


# ─────────────────────────────────────────────
# 自定义异常
# ─────────────────────────────────────────────

class AccountsFormatError(Exception):
    """accounts.conf 格式错误。"""
    pass


# ─────────────────────────────────────────────
# 初始化 README.txt
# ─────────────────────────────────────────────

README_CONTENT = """TJKEY 灾难恢复说明
==================

如果主程序 vault.exe 无法使用，可以用 recover.py 手动解密数据。

【运行要求】
  安装了 Python 3.11+ 和 cryptography 库。
  安装 cryptography：pip install cryptography
  recover.py 需与同目录的 markdown_export.py 一起使用（该文件为纯标准库）。

【使用方法】
  python recover.py <vault文件路径>

【示例】
  python recover.py "C:\\MyVault\\vaults\\main.vault"
  （Mac/Linux）python3 recover.py "/Users/xxx/MyVault/vaults/main.vault"

运行后程序会提示输入登录密码，验证通过后将解密结果保存为：
  main_recovered_YYYYMMDD_HHMMSS.json   （完整 JSON，所有字段明文）
  main_recovered_YYYYMMDD_HHMMSS.md     （Markdown 格式，便于阅读）

【加密算法信息】
  加密算法：AES-256-GCM（业界标准，Python cryptography 库支持）
  密钥派生：PBKDF2-HMAC-SHA256，60万次迭代
  每个加密字段独立加密，互不影响

【重要提示】
  * recover.py 和 vault_admin.py 在 VaultApp 程序文件夹中
  * 导出的文件包含所有明文密码，请妥善保管并及时删除
  * MyVault 文件夹本身不含任何密钥，密钥只在内存中
"""


def init_readme(myVault_path: str) -> None:
    """
    在 MyVault 目录下创建 README.txt（若已存在则不覆盖）。
    """
    readme_path = os.path.join(myVault_path, "README.txt")
    if not os.path.isfile(readme_path):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(README_CONTENT)


# ─────────────────────────────────────────────
# 模块自测
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("=== TJKEY accounts.py 自测 ===\n")

    with tempfile.TemporaryDirectory() as tmpdir:

        # 1. app.config 读写
        vault_config_path = write_app_config(tmpdir, tmpdir)
        read_back = read_app_config(tmpdir)
        assert read_back == tmpdir, f"期望 {tmpdir}, 实际 {read_back}"
        print(f"[1] [OK] app.config 读写正常: {read_back}")

        # 2. app.conf 读写
        conf = load_app_conf(tmpdir)
        assert conf["theme"] == "dark"
        conf2 = update_app_conf(tmpdir, theme="light", auto_lock_minutes=5)
        assert conf2["theme"] == "light"
        assert conf2["auto_lock_minutes"] == 5
        print("[2] [OK] app.conf 读写正常")

        # 3. 创建账号
        os.makedirs(os.path.join(tmpdir, "vaults"), exist_ok=True)
        acc = create_account(tmpdir, "main", "大号", "password123", "export456")
        print(f"[3] 创建账号: {acc['username']} ({acc['display_name']})")
        print("    [OK] 账号创建正常")

        # 4. 验证登录密码
        accounts_data = load_accounts(tmpdir)
        assert verify_login(accounts_data, "main", "password123")
        assert not verify_login(accounts_data, "main", "wrong")
        assert not verify_login(accounts_data, "notexist", "password123")
        print("[4] [OK] 登录密码验证正常")

        # 5. 验证导出密码
        assert verify_export_password(accounts_data, "main", "export456")
        assert not verify_export_password(accounts_data, "main", "wrong")
        print("[5] [OK] 导出密码验证正常")

        # 6. 重复用户名
        try:
            create_account(tmpdir, "main", "大号2", "pwd", "exp")
            print("    [FAIL] 应该抛出 ValueError！")
        except ValueError as e:
            print(f"[6] [OK] 重复用户名正确拒绝: {e}")

        # 7. 非法用户名
        try:
            create_account(tmpdir, "my account!", "测试", "pwd", "exp")
            print("    [FAIL] 应该抛出 ValueError！")
        except ValueError as e:
            print(f"[7] [OK] 非法用户名正确拒绝: {e}")

        # 8. 创建第二个账号
        create_account(tmpdir, "sub1", "小号1", "sub_pass", "sub_export")
        accounts_data = load_accounts(tmpdir)
        assert len(list_usernames(accounts_data)) == 2
        assert get_default_username(accounts_data) == "main"
        print("[8] [OK] 多账号创建正常，默认账号正确")

        # 9. 修改密码
        ok = change_password(tmpdir, "main", "password123", "newpass789")
        assert ok
        accounts_data = load_accounts(tmpdir)
        assert verify_login(accounts_data, "main", "newpass789")
        assert not verify_login(accounts_data, "main", "password123")
        print("[9] [OK] 修改登录密码正常")

        # 10. 修改密码时同步重新加密 vault
        from vault_io import create_empty_vault, load_vault, save_vault
        from crypto import (derive_key, encrypt_field, decrypt_field,
                            DecryptError, build_field_aad)

        vault_path = os.path.join(tmpdir, "vaults", "main.vault")
        vdata = create_empty_vault(vault_path, "main")
        salt = vdata["kdf_params"]["salt"]
        key_old = derive_key("newpass789", salt)
        enc_aad = build_field_aad("entry_test1", "fld_001")
        vdata["entries"].append({
            "id": "entry_test1", "name": "测试条目",
            "category_id": None, "subcategory_id": None, "order": 0,
            "created_at": now_iso(), "updated_at": now_iso(),
            "fields": [{"id": "fld_001", "label": "密码", "type": "secret",
                        "value": encrypt_field("topsecret", key_old,
                                               aad=enc_aad), "order": 0}],
        })
        save_vault(vault_path, vdata)

        ok = change_password(tmpdir, "main", "newpass789", "finalpass000")
        assert ok
        accounts_data = load_accounts(tmpdir)
        assert verify_login(accounts_data, "main", "finalpass000")
        # 新密码能解密重加密后的数据（version 2，带 AAD）
        loaded = load_vault(vault_path)
        assert loaded["version"] == 2, "改密重加密不应改变 version"
        enc_val = loaded["entries"][0]["fields"][0]["value"]
        key_new = derive_key("finalpass000", salt)
        assert decrypt_field(enc_val, key_new, aad=enc_aad) == "topsecret"
        # 旧密码不应能解密
        try:
            decrypt_field(enc_val, key_old, aad=enc_aad)
            print("    [FAIL] 旧密码不应能解密新数据！")
        except DecryptError:
            pass
        print("[10] [OK] 修改登录密码时 vault 已用新密码重新加密（保持 v2+AAD）")

        # 11. 改密中断自愈：模拟 vault 已重加密但哈希未更新的中断状态
        accounts_data = load_accounts(tmpdir)
        acc = get_account(accounts_data, "main")
        acc["password_hash"] = hash_password("newpass789")
        save_accounts(tmpdir, accounts_data)

        ok = change_password(tmpdir, "main", "newpass789", "finalpass000")
        assert ok
        accounts_data = load_accounts(tmpdir)
        assert verify_login(accounts_data, "main", "finalpass000")
        print("[11] [OK] 改密中断场景可自愈（vault 已重加密时仅补更新哈希）")

        # 12. 设置默认账号
        set_default_account(tmpdir, "sub1")
        accounts_data = load_accounts(tmpdir)
        assert get_default_username(accounts_data) == "sub1"
        print("[12] [OK] 设置默认账号正常")

        # 13. 删除账号
        ok = delete_account(tmpdir, "sub1", "sub_pass")
        assert ok
        accounts_data = load_accounts(tmpdir)
        assert len(list_usernames(accounts_data)) == 1
        # 默认账号应切换到 main
        assert get_default_username(accounts_data) == "main"
        print("[13] [OK] 删除账号正常，默认账号自动切换")

        # 14. README 初始化
        init_readme(tmpdir)
        assert os.path.isfile(os.path.join(tmpdir, "README.txt"))
        print("[14] [OK] README.txt 初始化正常")

        # 15. vault 路径穿越防护
        accounts_data = load_accounts(tmpdir)
        accounts_data["accounts"].append({
            "username": "evil", "display_name": "evil",
            "vault_file": "../../evil.vault",
            "password_hash": "x", "export_password_hash": "x",
        })
        assert get_vault_path(tmpdir, accounts_data, "evil") == ""
        assert get_vault_path(tmpdir, accounts_data, "main") == \
            os.path.abspath(os.path.join(tmpdir, "vaults", "main.vault"))
        print("[15] [OK] vault 路径穿越防护正常")

    print("\n=== 全部测试通过 [OK] ===")
