# vault_admin.py
# TJKEY 账户管理脚本
#
# 用途：创建、修改、删除账号，管理 accounts.conf
# 运行方式：python vault_admin.py
# 不需要打包成 exe，直接作为 .py 文件使用
#
# 依赖：cryptography（pip install cryptography）
# 不依赖 PySide6，纯命令行交互

import os
import sys
import getpass

# 确保能找到同目录下的其他模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from accounts import (
    read_app_config, write_app_config,
    load_accounts, save_accounts,
    create_account, delete_account,
    change_password, change_export_password,
    set_default_account, update_display_name,
    verify_login, verify_export_password,
    get_account, list_usernames, get_default_username,
    get_vault_path, init_readme,
    get_accounts_path,
)
from vault_io import (
    create_empty_vault, load_vault, VaultReencryptError,
    migrate_aad_format,
)
from crypto import now_iso, derive_key


# ─────────────────────────────────────────────
# 终端显示工具
# ─────────────────────────────────────────────

def clear():
    """清屏（跨平台）。"""
    os.system("cls" if os.name == "nt" else "clear")


def hr():
    """打印分隔线。"""
    print("─" * 48)


def title(text: str):
    """打印标题行。"""
    print(f"\n{'─' * 48}")
    print(f"  {text}")
    print(f"{'─' * 48}")


def success(msg: str):
    print(f"  [OK]  {msg}")


def error(msg: str):
    print(f"  [FAIL]  {msg}")


def info(msg: str):
    print(f"  ->  {msg}")


def warn(msg: str):
    print(f"  [!]  {msg}")


def prompt(text: str, default: str = "") -> str:
    """普通输入提示。"""
    if default:
        result = input(f"  {text} [{default}]：").strip()
        return result if result else default
    return input(f"  {text}：").strip()


def prompt_password(text: str) -> str:
    """密码输入（不回显）。"""
    return getpass.getpass(f"  {text}：")


def confirm(text: str) -> bool:
    """是/否确认，默认否。"""
    ans = input(f"  {text} (y/N)：").strip().lower()
    return ans == "y"


def press_enter():
    """等待用户按回车继续。"""
    input("\n  按 Enter 继续...")


# ─────────────────────────────────────────────
# 配置 MyVault 路径
# ─────────────────────────────────────────────

def get_or_setup_vault_path() -> str:
    """
    获取 MyVault 路径：
      1. 先读 app.config（程序目录）
      2. 若不存在或路径无效，引导用户输入并保存
    返回有效的 MyVault 绝对路径。
    """
    app_dir = os.path.dirname(os.path.abspath(__file__))
    myVault_path = read_app_config(app_dir)

    if myVault_path and os.path.isdir(myVault_path):
        return myVault_path

    # 引导配置
    print()
    print("  未找到 MyVault 数据文件夹配置。")
    print("  请输入 MyVault 文件夹的完整路径。")
    print("  （例如：C:\\Users\\xxx\\OneDrive\\MyVault）")
    print()

    while True:
        path = input("  MyVault 路径：").strip().strip('"').strip("'")
        if not path:
            continue
        if not os.path.isdir(path):
            ans = input(f"  文件夹 '{path}' 不存在，是否创建？(y/N)：").strip().lower()
            if ans == "y":
                try:
                    os.makedirs(path, exist_ok=True)
                    success(f"已创建文件夹：{path}")
                except OSError as e:
                    error(f"创建失败：{e}")
                    continue
            else:
                continue

        write_app_config(app_dir, path)
        success(f"已保存 MyVault 路径：{path}")
        return path


# ─────────────────────────────────────────────
# 显示账号列表
# ─────────────────────────────────────────────

def show_account_list(myVault_path: str) -> dict | None:
    """
    显示当前所有账号，返回 accounts_data 或 None（若无账号）。
    """
    accounts_path = get_accounts_path(myVault_path)
    if not os.path.isfile(accounts_path):
        return None

    try:
        accounts_data = load_accounts(myVault_path)
    except Exception:
        return None

    accounts = accounts_data.get("accounts", [])
    default = get_default_username(accounts_data)

    if not accounts:
        return accounts_data

    print()
    print("  当前账号：")
    for acc in accounts:
        username = acc["username"]
        display = acc["display_name"]
        tag = " [默认]" if username == default else ""
        print(f"    · {username}（{display}）{tag}")

    return accounts_data


# ─────────────────────────────────────────────
# 功能：创建账号
# ─────────────────────────────────────────────

def menu_create_account(myVault_path: str):
    title("创建新账号")

    # 输入用户名
    while True:
        username = prompt("账号用户名（仅字母、数字、下划线，如 sub1）")
        if not username:
            error("用户名不能为空")
            continue
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            error("用户名只允许字母、数字和下划线")
            continue
        break

    # 输入显示名称
    display_name = prompt("显示名称（如 小号1）", default=username)

    # 输入登录密码
    while True:
        pwd = prompt_password("登录密码")
        if not pwd:
            error("密码不能为空")
            continue
        pwd2 = prompt_password("再次输入登录密码（确认）")
        if pwd != pwd2:
            error("两次输入的密码不一致，请重新输入")
            continue
        break

    # 输入导出密码
    print()
    info("导出密码用于导出明文数据，可与登录密码不同（建议不同）")
    while True:
        exp = prompt_password("导出密码")
        if not exp:
            error("导出密码不能为空")
            continue
        exp2 = prompt_password("再次输入导出密码（确认）")
        if exp != exp2:
            error("两次输入的导出密码不一致，请重新输入")
            continue
        break

    # 确认
    print()
    info(f"即将创建账号：{username}（{display_name}）")
    if not confirm("确认创建？"):
        info("已取消")
        press_enter()
        return

    # 执行创建
    print()
    try:
        # 确保 vaults 目录存在
        vaults_dir = os.path.join(myVault_path, "vaults")
        os.makedirs(vaults_dir, exist_ok=True)

        # 创建账号配置
        new_acc = create_account(myVault_path, username, display_name, pwd, exp)
        success(f"账号 '{username}' 创建成功")

        # 创建空白 vault 文件
        vault_path = os.path.join(myVault_path, new_acc["vault_file"])
        create_empty_vault(vault_path, username)
        success(f"已创建数据文件：{new_acc['vault_file']}")

        # 初始化 README
        init_readme(myVault_path)
        success("已更新 README.txt")

    except ValueError as e:
        error(str(e))
    except Exception as e:
        error(f"创建失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：修改登录密码
# ─────────────────────────────────────────────

def menu_change_password(myVault_path: str):
    title("修改登录密码")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入要修改的账号用户名")
    if not get_account(accounts_data, username):
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    old_pwd = prompt_password("当前登录密码")
    if not verify_login(accounts_data, username, old_pwd):
        error("当前密码错误")
        press_enter()
        return

    while True:
        new_pwd = prompt_password("新登录密码")
        if not new_pwd:
            error("密码不能为空")
            continue
        new_pwd2 = prompt_password("再次输入新密码（确认）")
        if new_pwd != new_pwd2:
            error("两次输入不一致")
            continue
        break

    print()
    warn("修改登录密码会同时用新密码重新加密该账号的数据文件。")
    warn("请确认 TJKEY 主程序已完全关闭，否则可能造成数据不一致！")
    if not confirm("继续修改吗？"):
        info("已取消")
        press_enter()
        return

    print()
    try:
        ok = change_password(myVault_path, username, old_pwd, new_pwd)
        if ok:
            success(f"账号 '{username}' 的登录密码已修改，数据文件已重新加密")
        else:
            error("修改失败（密码验证失败）")
    except VaultReencryptError as e:
        error(f"修改失败：{e}")
        info("如需抢救数据，可用 recover.py 尝试解密（见 MyVault/README.txt）")
    except Exception as e:
        error(f"修改失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：修改导出密码
# ─────────────────────────────────────────────

def menu_change_export_password(myVault_path: str):
    title("修改导出密码")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入要修改的账号用户名")
    if not get_account(accounts_data, username):
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    # 需要验证登录密码才能修改导出密码（双重保护）
    login_pwd = prompt_password("请输入该账号的登录密码（验证身份）")
    if not verify_login(accounts_data, username, login_pwd):
        error("登录密码错误")
        press_enter()
        return

    old_exp = prompt_password("当前导出密码")
    if not verify_export_password(accounts_data, username, old_exp):
        error("当前导出密码错误")
        press_enter()
        return

    while True:
        new_exp = prompt_password("新导出密码")
        if not new_exp:
            error("密码不能为空")
            continue
        new_exp2 = prompt_password("再次输入新导出密码（确认）")
        if new_exp != new_exp2:
            error("两次输入不一致")
            continue
        break

    print()
    try:
        ok = change_export_password(myVault_path, username, old_exp, new_exp)
        if ok:
            success(f"账号 '{username}' 的导出密码已修改")
        else:
            error("修改失败")
    except Exception as e:
        error(f"修改失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：修改显示名称
# ─────────────────────────────────────────────

def menu_change_display_name(myVault_path: str):
    title("修改账号显示名称")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入要修改的账号用户名")
    acc = get_account(accounts_data, username)
    if not acc:
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    current_name = acc.get("display_name", username)
    new_name = prompt(f"新显示名称", default=current_name)

    if new_name == current_name:
        info("名称未改变")
        press_enter()
        return

    try:
        update_display_name(myVault_path, username, new_name)
        success(f"账号 '{username}' 的显示名称已改为：{new_name}")
    except Exception as e:
        error(f"修改失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：设置默认账号
# ─────────────────────────────────────────────

def menu_set_default(myVault_path: str):
    title("设置默认登录账号")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入要设为默认的账号用户名")
    if not get_account(accounts_data, username):
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    try:
        set_default_account(myVault_path, username)
        success(f"默认账号已设置为：{username}")
    except Exception as e:
        error(f"设置失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：删除账号
# ─────────────────────────────────────────────

def menu_delete_account(myVault_path: str):
    title("删除账号")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入要删除的账号用户名")
    acc = get_account(accounts_data, username)
    if not acc:
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    display = acc.get("display_name", username)
    vault_rel = acc.get("vault_file", "")

    # 警告
    print()
    warn(f"即将永久删除账号：{username}（{display}）")
    warn(f"对应数据文件：{vault_rel}")
    warn("此操作不可逆，数据文件将被永久删除！")
    print()

    if not confirm("确认要删除吗？"):
        info("已取消")
        press_enter()
        return

    # 需要输入登录密码确认
    pwd = prompt_password("请输入该账号的登录密码以最终确认")
    if not verify_login(accounts_data, username, pwd):
        error("密码错误，删除取消")
        press_enter()
        return

    # 再次确认
    confirm_text = input('  请输入"确认删除"以继续：').strip()
    if confirm_text != "确认删除":
        info("输入不匹配，删除取消")
        press_enter()
        return

    print()
    try:
        ok = delete_account(myVault_path, username, pwd)
        if ok:
            success(f"账号 '{username}' 及其数据文件已删除")
        else:
            error("删除失败（密码验证失败）")
    except Exception as e:
        error(f"删除失败：{e}")

    press_enter()


# ─────────────────────────────────────────────
# 功能：升级/降级数据文件格式（version 1 ⇄ 2）
# ─────────────────────────────────────────────

def menu_migrate_format(myVault_path: str):
    title("升级/降级数据文件格式")

    accounts_data = show_account_list(myVault_path)
    if not accounts_data or not accounts_data.get("accounts"):
        error("当前没有任何账号")
        press_enter()
        return

    username = prompt("请输入账号用户名")
    if not get_account(accounts_data, username):
        error(f"账号 '{username}' 不存在")
        press_enter()
        return

    vault_path = get_vault_path(myVault_path, accounts_data, username)
    if not vault_path or not os.path.isfile(vault_path):
        error(f"找不到账号 '{username}' 的数据文件")
        press_enter()
        return

    try:
        data = load_vault(vault_path)
    except Exception as e:
        error(f"读取数据文件失败：{e}")
        press_enter()
        return

    cur = data.get("version", 1)
    if cur == 2:
        info(f"账号 {username} 当前为 version 2，将降级到 version 1（供回退旧版程序）")
        target = 1
    else:
        info(f"账号 {username} 当前为 version {cur}，将升级到 version 2（密文绑定条目/字段 ID）")
        target = 2

    print()
    warn("转换会重写整个数据文件，期间请勿断电！")
    warn("请先完全退出 TJKEY 主程序，否则可能造成数据不一致！")
    if not confirm("继续吗？"):
        info("已取消")
        press_enter()
        return

    pwd = prompt_password("请输入该账号的登录密码以确认身份")
    if not verify_login(accounts_data, username, pwd):
        error("密码错误，已取消")
        press_enter()
        return

    print()
    try:
        kdf = data.get("kdf_params", {})
        salt = kdf.get("salt", "")
        iterations = kdf.get("iterations", 600000)
        key = derive_key(pwd, salt, iterations)
        n = migrate_aad_format(vault_path, key, target_version=target)
        success(f"已迁移到 version {target}，转换 {n} 个加密字段")
        if target == 1:
            warn("降级为旧格式：请改用旧版程序打开；新版程序登录时会再自动升级到 version 2。")
        else:
            info("升级完成：云同步的其他电脑须先升级程序，再打开数据文件。")
    except Exception as e:
        error(f"迁移失败：{e}")
        info("数据文件保持迁移前状态，可重试")

    press_enter()


# ─────────────────────────────────────────────
# 主菜单
# ─────────────────────────────────────────────

def main():
    clear()
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║         TJKEY  账户管理工具              ║")
    print("  ╚══════════════════════════════════════════╝")

    # 获取 MyVault 路径
    myVault_path = get_or_setup_vault_path()
    print(f"\n  数据文件夹：{myVault_path}")

    while True:
        print()
        accounts_data = show_account_list(myVault_path)
        hr()
        print("  请选择操作：")
        print("    [1] 创建新账号")
        print("    [2] 修改登录密码")
        print("    [3] 修改导出密码")
        print("    [4] 修改账号显示名称")
        print("    [5] 设置默认登录账号")
        print("    [6] 删除账号")
        print("    [7] 升级/降级数据文件格式")
        print("    [0] 退出")
        hr()

        choice = input("  请输入选项：").strip()

        if choice == "1":
            menu_create_account(myVault_path)
        elif choice == "2":
            menu_change_password(myVault_path)
        elif choice == "3":
            menu_change_export_password(myVault_path)
        elif choice == "4":
            menu_change_display_name(myVault_path)
        elif choice == "5":
            menu_set_default(myVault_path)
        elif choice == "6":
            menu_delete_account(myVault_path)
        elif choice == "7":
            menu_migrate_format(myVault_path)
        elif choice == "0":
            print()
            info("退出账户管理工具")
            print()
            sys.exit(0)
        else:
            error("无效选项，请重新输入")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  已退出（Ctrl+C）\n")
        sys.exit(0)
