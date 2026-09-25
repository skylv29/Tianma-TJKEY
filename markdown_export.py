# markdown_export.py
# TJKEY Markdown 导出（共享模块）
#
# 被 ui/export_dialog.py（程序内导出）和 recover.py（灾难恢复）共用。
# 只依赖标准库，不依赖 PySide6 / crypto.py，保证 recover.py 的独立可用性。
#
# 输入约定：
#   vault dict 中 secret 字段的 value 必须已经是明文
#   （调用方负责解密；解密失败的字段由调用方替换为占位文本）。

import os
from datetime import datetime


def _md_escape_cell(value: str) -> str:
    """转义 Markdown 表格单元格内容（竖线会截断表格列）。"""
    return str(value).replace("|", "｜")


def _append_secret_block(lines: list, label: str, value: str) -> None:
    """以围栏代码块输出 secret 值，围栏长度自适应。

    值本身包含 ``` 时，用更长的围栏（````）才能正确包裹，
    否则代码块会被值中的围栏提前截断。
    """
    fence = "```"
    while fence in value:
        fence += "`"
    lines.append(f"**{label}**")
    lines.append("")
    lines.append(fence)
    lines.append(value)
    lines.append(fence)
    lines.append("")


def build_markdown(vault_data: dict, include_deleted: bool = False) -> str:
    """
    将 vault dict（secret 已解密）导出为 Markdown 字符串。

    结构：# 大类 → ## 小类 → ### 条目；
    text / date / date_domain / URL / 标签用表格，secret 用代码块。

    参数：
        include_deleted - 是否包含回收站条目（deleted 标记）。
                          程序内导出默认排除；recover.py 灾难恢复
                          传 True 全量导出，不丢任何数据。
    """
    lines = []
    account = vault_data.get("account", "未知")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines += [
        "# TJKEY 数据导出",
        "",
        f"- **账号**：{account}",
        f"- **导出时间**：{now}",
        "- **⚠️ 警告**：本文件包含所有明文密码，请妥善保管，阅后删除",
        "",
        "---",
        "",
    ]

    entries = vault_data.get("entries", [])
    if not include_deleted:
        entries = [e for e in entries if not e.get("deleted")]
    categories = vault_data.get("categories", [])

    # 分类查找表（按 order 排序）
    cat_map = {}
    for cat in sorted(categories, key=lambda c: c.get("order", 0)):
        subs = {
            s["id"]: s["name"]
            for s in sorted(cat.get("subcategories", []),
                            key=lambda s: s.get("order", 0))
        }
        cat_map[cat["id"]] = {"name": cat["name"], "subs": subs,
                              "order": cat.get("order", 0)}

    # 按大类分组：cat_id -> {sub_id 或 "__none__": [entries]}
    groups = {}
    uncategorized = []
    known_cat_ids = {c["id"] for c in categories}

    for entry in sorted(entries, key=lambda e: e.get("order", 0)):
        cat_id = entry.get("category_id")
        sub_id = entry.get("subcategory_id")
        if cat_id is None or cat_id not in known_cat_ids:
            # 未分类，或分类已被删除（孤儿条目）——归入未分类，
            # 避免归组后因找不到对应大类标题而静默丢失
            uncategorized.append(entry)
        else:
            groups.setdefault(cat_id, {})
            key = sub_id if sub_id else "__none__"
            groups[cat_id].setdefault(key, []).append(entry)

    # 按大类顺序输出
    for cat_id, cat_info in sorted(cat_map.items(),
                                   key=lambda x: x[1]["order"]):
        if cat_id not in groups:
            continue
        lines.append(f"# {cat_info['name']}")
        lines.append("")

        sub_groups = groups[cat_id]
        for sub_id, sub_name in cat_info["subs"].items():
            if sub_id not in sub_groups:
                continue
            lines.append(f"## {sub_name}")
            lines.append("")
            for entry in sub_groups[sub_id]:
                _append_entry(lines, entry)

        if "__none__" in sub_groups:
            for entry in sub_groups["__none__"]:
                _append_entry(lines, entry)

    # 未分类
    if uncategorized:
        lines.append("# 未分类")
        lines.append("")
        for entry in uncategorized:
            _append_entry(lines, entry)

    return "\n".join(lines)


def _append_entry(lines: list, entry: dict) -> None:
    """向 lines 追加单个条目的 Markdown 内容。"""
    name = entry.get("name", "（未命名）")
    url = entry.get("url", "")
    tags = entry.get("tags", [])
    fields = sorted(entry.get("fields", []), key=lambda f: f.get("order", 0))

    lines.append(f"### {name}")
    lines.append("")

    # 表格字段（text / date / date_domain / URL / 标签）
    table_rows = []
    if url:
        table_rows.append(("网址", url))

    for f in fields:
        ftype = f.get("type", "text")
        label = f.get("label", "")
        value = f.get("value", "")
        if not value or ftype == "secret":
            continue
        if ftype == "date_domain" and "|" in value:
            domain, expire = value.split("|", 1)
            table_rows.append((label, f"{domain.strip()}（到期：{expire.strip()}）"))
        else:
            table_rows.append((label, value))

    if tags:
        table_rows.append(("标签", "、".join(tags)))

    if table_rows:
        lines.append("| 字段 | 值 |")
        lines.append("|------|-----|")
        for lbl, val in table_rows:
            # 标签和值都来自用户输入，都可能含竖线
            lines.append(f"| {_md_escape_cell(lbl)} | {_md_escape_cell(val)} |")
        lines.append("")

    # 代码块字段（secret，输入数据中应已解密为明文）
    for f in fields:
        if f.get("type") != "secret":
            continue
        label = f.get("label", "")
        value = f.get("value", "")
        if not value:
            continue
        _append_secret_block(lines, label, value)

    # 备注（单独段落；主程序当前不生成该字段，兼容旧数据）
    notes = entry.get("notes", "")
    if notes:
        lines.append(f"**备注**：{notes}")
        lines.append("")

    lines.append("---")
    lines.append("")


def restrict_file_permissions(path: str) -> None:
    """
    尽力限制明文导出文件的读取权限。

    POSIX：仅属主可读写（0o600）；
    Windows：os.chmod 无 ACL 语义，静默跳过，权限由目录继承规则决定。
    """
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
