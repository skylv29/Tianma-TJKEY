# TJKEY — 本地字段级加密密码管理器
## 完整项目设计文档 v1.2

> v1.1（2026-09-08）：补全源代码目录结构、更新接口约定，
> 新增第 23 章（代码审查与安全加固记录）与第 24 章（测试与验证）。

> v1.2（2026-09-23）：vault 文件格式升级 version 1 → 2（AAD 字段
> 位置绑定），登录自动升版、vault_admin 菜单 [7] 升降级回退、
> recover.py 双版本兼容、AAD 双实现防漂移测试；
> 多机云同步须所有机器先升级程序再打开数据文件。

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [文件结构](#3-文件结构)
4. [配置文件规范](#4-配置文件规范)
5. [数据文件规范](#5-数据文件规范)
6. [加密与解密逻辑](#6-加密与解密逻辑)
7. [账户系统](#7-账户系统)
8. [主程序界面设计](#8-主程序界面设计)
9. [条目模板系统](#9-条目模板系统)
10. [分类与导航系统](#10-分类与导航系统)
11. [到期提醒系统](#11-到期提醒系统)
12. [搜索系统](#12-搜索系统)
13. [查看与编辑模式](#13-查看与编辑模式)
14. [导出系统](#14-导出系统)
15. [自动锁屏](#15-自动锁屏)
16. [云盘冲突检测](#16-云盘冲突检测)
17. [主题系统](#17-主题系统)
18. [vault_admin.py 管理脚本](#18-vault_adminpy-管理脚本)
19. [recover.py 灾难恢复脚本](#19-recoverpy-灾难恢复脚本)
20. [打包配置](#20-打包配置)
21. [开发顺序建议](#21-开发顺序建议)
22. [各模块接口约定](#22-各模块接口约定)
23. [代码审查与安全加固记录](#23-代码审查与安全加固记录)
24. [测试与验证](#24-测试与验证)
25. [功能补全记录（P4）](#25-功能补全记录p4)
26. [可靠性增强记录（P5）](#26-可靠性增强记录p5)
27. [单机升级与双机并存操作指引](#27-单机升级与双机并存操作指引)

---

## 1. 项目概述

### 1.1 项目背景

TJKEY 是一款本地优先的个人密码管理器，专为以下场景设计：

- 用户有多个网站账户，需要分类记录用户名、密码及其他附属信息
- 部分账户有 API Key、域名、到期时间、密保问题等额外字段
- 数据通过云盘文件夹自动同步到多台电脑
- 用户无编程基础，软件后续维护通过 AI 辅助完成

### 1.2 核心设计原则

- **字段级加密**：敏感字段单独加密，账户名称、分类等结构信息明文存储，保证即使加密软件消失也能通过标准工具恢复数据
- **程序与数据分离**：可执行程序放在任意位置，数据文件夹独立存放并同步至云盘
- **多账号隔离**：支持多个独立账号（大号/小号），每个账号有独立的数据文件、分类结构和导出密码
- **零网络依赖**：软件完全本地运行，不访问任何网络
- **可恢复性**：加密算法使用业界标准，附带独立的灾难恢复脚本，软件消失后仍可手动解密

### 1.3 软件组成

| 文件 | 类型 | 说明 |
|---|---|---|
| `TJ-KEY.exe` | 可执行程序 | 主程序，日常使用入口 |
| `vault_admin.py` | Python 脚本 | 账户管理工具（创建/修改/删除账号） |
| `recover.py` | Python 脚本 | 灾难恢复工具，无需 PySide6，纯标准库 |

---

## 2. 技术栈与依赖

### 2.1 开发语言与框架

- **Python 3.11+**
- **PySide6**：UI 框架（Qt6 Python 绑定）

### 2.2 核心依赖库

```
PySide6>=6.6.0,<7.0.0         # UI 框架
cryptography>=42.0.0,<50.0.0  # 加密库（AES-256-GCM、PBKDF2）
```

### 2.3 标准库（无需安装）

```
json        # 数据文件读写
os          # 文件路径操作
sys         # 系统参数
hashlib     # 密码哈希与密钥派生
base64      # 加密数据编码
secrets     # 常量时间比较、随机 ID 生成
datetime    # 到期时间计算、时间戳
urllib.parse  # URL 协议解析（打开网址前的白名单校验）
```

### 2.4 打包工具

```
PyInstaller>=6.0.0    # 打包成 exe
```

### 2.5 为什么选择 PySide6

- Python 是 AI 训练数据最丰富的语言，AI 维护成本最低
- PySide6 提供现代 Qt6 界面，支持深色/浅色主题
- onedir 打包模式启动速度约 1-2 秒，优于 onefile 的 3-5 秒
- 报错信息可直接阅读，便于非开发者向 AI 求助排查问题

---

## 3. 文件结构

### 3.1 完整目录结构

```
📁 VaultApp/                        ← 程序本体，可放任意本地路径
    📄 TJ-KEY.exe                   ← 主程序（PyInstaller 打包）
    📄 main.py                      ← 程序入口（源码运行时使用）
    📄 session.py                   ← 全局会话状态（内存中的密钥与 vault 数据）
    📄 crypto.py                    ← 加密核心（AES-256-GCM / PBKDF2）
    📄 vault_io.py                  ← vault 文件读写、CRUD、外部修改检测
    📄 accounts.py                  ← accounts.conf / app.conf 读写与账户逻辑
    📄 markdown_export.py           ← Markdown 导出共享模块（导出对话框/恢复工具共用）
    📄 icons.py                     ← SVG 图标资源（基于 Feather Icons）
    📄 version.py                   ← 应用版本号（单一来源）
    📄 system_lock.py               ← 系统锁屏探测（Windows 会话锁定联动）
    📄 vault_admin.py               ← 账户管理脚本（不打包，直接运行）
    📄 recover.py                   ← 灾难恢复脚本（不打包，直接运行）
    📄 app.config                   ← 记录 MyVault 数据文件夹的绝对路径
    📄 requirements.txt             ← 运行时依赖（含版本上限）
    📄 requirements-dev.txt         ← 开发/测试依赖（pytest）
    📄 pytest.ini                   ← pytest 配置（testpaths=tests）
    📄 CHANGELOG.md                 ← 版本变更记录
    📄 .gitignore                   ← 排除 app.config / __pycache__ / 打包产物
    📁 tests/
        📄 test_suites.py           ← pytest 集成层（子进程运行全部验证脚本）
    📁 .github/workflows/
        📄 tests.yml                ← CI（Windows/Linux 矩阵运行全部验证）
    📁 ui/                          ← 界面模块
        📄 main_window.py           ← 主窗口（三栏布局、自动锁屏、系统锁屏联动）
        📄 login.py                 ← 登录窗口 + 首次启动引导 + 首次建号
        📄 nav_panel.py             ← 左侧分类导航（拖拽排序、回收站入口）
        📄 entry_list.py            ← 中间条目列表（搜索、拖拽排序、回收站视图）
        📄 entry_detail.py          ← 右侧详情面板（显示/复制/剪贴板清空）
        📄 entry_edit.py            ← 编辑面板（新建/修改、密码生成器、日期校验）
        📄 vault_sync.py            ← 统一保存入口（外部修改检测、强制锁屏）
        📄 change_password_dialog.py ← 修改登录密码对话框
        📄 export_dialog.py         ← 导出对话框（二级密码验证）
        📄 settings_dialog.py       ← 设置对话框（主题/锁屏时间/改密入口）
        📄 template_manager.py      ← 模板管理器
    📁 styles/                      ← 主题（QSS + 颜色常量）
        📄 __init__.py              ← 主题管理器
        📄 dark.py / light.py       ← 深色 / 浅色样式表
    📁 assets/                      ← 图标资源（icon.ico / icon.png）
    📁 _internal/                   ← PyInstaller 打包依赖（自动生成）
        ...

📁 MyVault/                         ← 数据文件夹，放入云盘同步目录
    📄 accounts.conf                ← 账户注册表（JSON 格式）
    📄 app.conf                     ← 全局偏好配置（主题等）
    📁 vaults/
        📄 main.vault               ← 大号的完整数据文件
        📄 sub1.vault               ← 小号1的完整数据文件
        📄 sub2.vault               ← 小号2的完整数据文件
    📄 README.txt                   ← 灾难恢复说明文档（纯文本）
```

### 3.2 各文件职责说明

| 文件 | 可手动编辑 | 说明 |
|---|---|---|
| `app.config` | 可以 | 只有一行：MyVault 文件夹的绝对路径 |
| `accounts.conf` | 谨慎编辑 | 账户列表，通过 vault_admin.py 管理 |
| `app.conf` | 不建议 | 主题偏好等，由主程序自动写入 |
| `*.vault` | 不要手动改 | 数据文件，由主程序读写 |
| `README.txt` | 可以 | 灾难恢复说明，建议保持原样 |

---

## 4. 配置文件规范

### 4.1 app.config（程序本体目录）

记录数据文件夹的绝对路径，**首次启动时由引导流程写入**。

```
D:\MyVault
```

- 只有一行，无格式，纯文本路径
- 程序启动时读取此文件，找到 `MyVault` 文件夹
- 若文件不存在或路径无效，触发首次启动引导流程

### 4.2 accounts.conf（MyVault 根目录）

存储所有账号的基本信息，**密码以哈希形式存储，永远不存明文**。

```json
{
  "default_account": "main",
  "accounts": [
    {
      "username": "main",
      "display_name": "大号",
      "vault_file": "vaults/main.vault",
      "password_hash": "pbkdf2:sha256:600000$<salt_hex>$<hash_hex>",
      "export_password_hash": "pbkdf2:sha256:600000$<salt_hex>$<hash_hex>",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    },
    {
      "username": "sub1",
      "display_name": "小号1",
      "vault_file": "vaults/sub1.vault",
      "password_hash": "pbkdf2:sha256:600000$<salt_hex>$<hash_hex>",
      "export_password_hash": "pbkdf2:sha256:600000$<salt_hex>$<hash_hex>",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00"
    }
  ]
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `default_account` | string | 登录界面预填的账号名 |
| `username` | string | 账号标识符，全局唯一，仅用字母数字下划线 |
| `display_name` | string | 界面显示名称 |
| `vault_file` | string | 相对于 MyVault 的 vault 文件路径 |
| `password_hash` | string | 登录密码的 PBKDF2 哈希，格式见第6节 |
| `export_password_hash` | string | 导出二级密码的哈希，独立于登录密码 |

### 4.3 app.conf（MyVault 根目录）

存储用户偏好配置，**由主程序自动读写，无需手动编辑**。

```json
{
  "theme": "dark",
  "auto_lock_minutes": 2,
  "last_account": "main",
  "window_geometry": {
    "width": 1100,
    "height": 720,
    "x": 100,
    "y": 100
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `theme` | string | `"dark"` | `"dark"` 或 `"light"` |
| `auto_lock_minutes` | int | `2` | 自动锁屏等待分钟数，0 表示禁用 |
| `last_account` | string | `"main"` | 上次登录的账号名，用于预填登录框 |
| `window_geometry` | object | 见上 | 窗口位置和大小，退出时自动保存 |

---

## 5. 数据文件规范

### 5.1 .vault 文件整体结构

每个账号对应一个 `.vault` 文件，本质是 JSON 格式，明文存储结构信息，敏感字段以 `ENC:` 前缀存储加密值。

```json
{
  "version": 2,
  "account": "main",
  "kdf_params": {
    "algorithm": "pbkdf2",
    "hash": "sha256",
    "iterations": 600000,
    "salt": "<base64_encoded_salt>"
  },
  "categories": [...],
  "templates": [...],
  "entries": [...]
}
```

**顶层字段说明：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | int | 文件格式版本号：1 = 旧格式（密文不绑定位置）；2 = 当前格式（AAD 绑定 entry_id+field_id，见 6.7）。新建文件直接生成 2；1 在登录时自动升级（见 23.1），菜单 [7] 可手动升降级（见 18） |
| `account` | string | 所属账号的 username |
| `kdf_params` | object | 密钥派生参数，用于从登录密码派生加密密钥 |
| `categories` | array | 分类树结构（含排序） |
| `templates` | array | 条目模板列表 |
| `entries` | array | 所有条目数据 |

> **云同步警告**：version 2 文件旧版程序会明确拒绝打开（"不支持的
> Vault 文件版本"）。多机共享同一云盘 MyVault 时，**必须所有机器
> 先升级程序，再打开数据文件**；回退旧版程序前先用 vault_admin
> 菜单 [7] 把文件降级回 version 1（见 18.6）。

### 5.2 kdf_params（密钥派生参数）

```json
{
  "algorithm": "pbkdf2",
  "hash": "sha256",
  "iterations": 600000,
  "salt": "BASE64_ENCODED_16_BYTES_RANDOM_SALT"
}
```

- `salt` 在 vault 文件首次创建时随机生成，之后固定不变
- 同一账号的所有加密字段共享同一个派生密钥
- 登录时用登录密码 + 此处的 salt 和参数派生密钥，存入内存

### 5.3 categories（分类树）

```json
"categories": [
  {
    "id": "cat_001",
    "name": "开发工具",
    "order": 0,
    "subcategories": [
      { "id": "sub_001", "name": "Google 系", "order": 0 },
      { "id": "sub_002", "name": "AI 平台", "order": 1 },
      { "id": "sub_003", "name": "代码托管", "order": 2 }
    ]
  },
  {
    "id": "cat_002",
    "name": "域名注册",
    "order": 1,
    "subcategories": [
      { "id": "sub_004", "name": "Cloudflare", "order": 0 },
      { "id": "sub_005", "name": "US.KG", "order": 1 },
      { "id": "sub_006", "name": "Namesilo", "order": 2 }
    ]
  },
  {
    "id": "cat_003",
    "name": "社交媒体",
    "order": 2,
    "subcategories": []
  }
]
```

**字段说明：**

| 字段 | 说明 |
|---|---|
| `id` | 唯一标识符，格式 `cat_XXX` / `sub_XXX`，创建时生成，不可修改 |
| `name` | 分类显示名称 |
| `order` | 排列顺序，从 0 开始，拖拽排序时更新此值 |
| `subcategories` | 二级分类数组，结构相同但无 subcategories |

### 5.4 templates（条目模板）

```json
"templates": [
  {
    "id": "tpl_builtin_001",
    "name": "通用账号",
    "is_builtin": true,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "备注", "type": "text" }
    ]
  },
  {
    "id": "tpl_builtin_002",
    "name": "域名账号",
    "is_builtin": true,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "域名", "type": "date_domain" },
      { "label": "备注", "type": "text" }
    ]
  },
  {
    "id": "tpl_builtin_003",
    "name": "开发平台",
    "is_builtin": true,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "API Key", "type": "secret" },
      { "label": "备注", "type": "text" }
    ]
  },
  {
    "id": "tpl_builtin_004",
    "name": "邮箱账号",
    "is_builtin": true,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "恢复邮箱", "type": "text" },
      { "label": "备注", "type": "text" }
    ]
  },
  {
    "id": "tpl_builtin_005",
    "name": "金融/支付",
    "is_builtin": true,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "绑定手机", "type": "text" },
      { "label": "密保问题", "type": "secret" },
      { "label": "备注", "type": "text" }
    ]
  },
  {
    "id": "tpl_custom_001",
    "name": "Cloudflare 专用",
    "is_builtin": false,
    "fields": [
      { "label": "用户名", "type": "text" },
      { "label": "密码", "type": "secret" },
      { "label": "API Token", "type": "secret" },
      { "label": "域名1", "type": "date_domain" },
      { "label": "域名2", "type": "date_domain" },
      { "label": "域名3", "type": "date_domain" },
      { "label": "备注", "type": "text" }
    ]
  }
]
```

**模板字段类型说明：**

| type 值 | 含义 | 存储方式 | 参与到期检测 |
|---|---|---|---|
| `text` | 普通文本 | 明文 | 否 |
| `secret` | 敏感信息 | ENC: 加密 | 否 |
| `date` | 日期 | 明文 YYYY-MM-DD | 是 |
| `date_domain` | 域名+到期日组合字段 | label 明文，value 格式 `域名\|YYYY-MM-DD` | 是 |

> `date_domain` 是特殊的复合类型：一个字段同时记录域名名称（明文）和到期时间（明文），在界面上显示为两列，在到期提醒中使用到期时间部分，在搜索中使用域名部分。

**模板规则：**
- `is_builtin: true` 的模板可修改字段但不可删除
- `is_builtin: false` 的自定义模板可增删改
- 模板只定义字段结构，不包含任何数据

### 5.5 entries（条目数据）

```json
"entries": [
  {
    "id": "entry_a1b2c3",
    "name": "Cloudflare 主号",
    "category_id": "cat_002",
    "subcategory_id": "sub_004",
    "url": "https://dash.cloudflare.com",
    "tags": ["cloudflare", "主力"],
    "order": 0,
    "created_at": "2025-01-01T12:00:00",
    "updated_at": "2025-06-01T08:30:00",
    "fields": [
      {
        "id": "fld_001",
        "label": "用户名",
        "type": "text",
        "value": "admin@gmail.com",
        "order": 0
      },
      {
        "id": "fld_002",
        "label": "密码",
        "type": "secret",
        "value": "ENC:BASE64ENCODED_IV_CIPHERTEXT_TAG",
        "order": 1
      },
      {
        "id": "fld_003",
        "label": "API Token",
        "type": "secret",
        "value": "ENC:BASE64ENCODED_IV_CIPHERTEXT_TAG",
        "order": 2
      },
      {
        "id": "fld_004",
        "label": "域名1",
        "type": "date_domain",
        "value": "example.com|2026-06-01",
        "order": 3
      },
      {
        "id": "fld_005",
        "label": "域名2",
        "type": "date_domain",
        "value": "mysite.net|2025-11-15",
        "order": 4
      },
      {
        "id": "fld_006",
        "label": "备注",
        "type": "text",
        "value": "主力账号，绑定信用卡 xxxx",
        "order": 5
      }
    ]
  }
]
```

**条目字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 唯一标识符，格式 `entry_XXXXXX`，创建时随机生成 |
| `name` | string | **是** | 条目名称，唯一的必填项 |
| `category_id` | string | 否 | 所属大类 ID，可为 null（未分类） |
| `subcategory_id` | string | 否 | 所属小类 ID，可为 null |
| `url` | string | 否 | 登录网址，选填 |
| `tags` | array | 否 | 标签列表，字符串数组 |
| `order` | int | 是 | 在当前分类内的排列顺序 |
| `fields` | array | 否 | 自定义字段数组 |
| `fields[].id` | string | 是 | 字段唯一标识符，格式 `fld_XXX` |
| `fields[].label` | string | 是 | 字段名称 |
| `fields[].type` | string | 是 | 字段类型：text / secret / date / date_domain |
| `fields[].value` | string | 否 | 字段值；secret 类型以 `ENC:` 开头 |
| `fields[].order` | int | 是 | 字段在条目内的排列顺序 |

---

## 6. 加密与解密逻辑

### 6.1 密钥派生（登录时执行一次）

```
用户输入的登录密码（明文字符串）
        +
vault 文件中的 kdf_params.salt（base64解码后的16字节随机值）
        +
vault 文件中的 kdf_params.iterations（迭代次数，当前为 600000）
        ↓
PBKDF2-HMAC-SHA256 算法
iterations = vault 内记录值（登录与 recover.py 一致按文件读取）
dklen = 32 字节（256 bit）
        ↓
32字节 AES 加密密钥
        ↓
存储在内存中的 session_key 变量
（锁屏/退出时调用 session_key = None 清除）
```

**Python 实现参考：**

```python
import hashlib
import os
import base64

MAX_KDF_ITERATIONS = 10_000_000   # 迭代次数上限，防止畸形配置卡死

def derive_key(password: str, salt_b64: str,
               iterations: int = 600000) -> bytes:
    # 登录/重加密时应传入 vault 文件 kdf_params.iterations 中记录的值：
    # 密钥由"密码+salt+迭代次数"共同决定，未来上调迭代次数后，
    # 旧 vault 仍能按其记录值登录（与 recover.py 行为一致）
    if not (1 <= iterations <= MAX_KDF_ITERATIONS):
        raise ValueError(f"无效的 KDF 迭代次数：{iterations!r}")
    salt = base64.b64decode(salt_b64)
    key = hashlib.pbkdf2_hmac(
        hash_name='sha256',
        password=password.encode('utf-8'),
        salt=salt,
        iterations=iterations,
        dklen=32
    )
    return key

def generate_salt() -> str:
    return base64.b64encode(os.urandom(16)).decode('utf-8')
```

### 6.2 加密单个 secret 字段（保存时触发）

```
明文字符串（用户输入的密码/API Key 等）
        +
session_key（内存中的32字节密钥）
        +
随机生成的 12 字节 IV（每次加密独立生成）
        ↓
AES-256-GCM 加密
        ↓
输出：12字节 IV + 密文 + 16字节认证标签
        ↓
base64 编码
        ↓
"ENC:" + base64编码结果
        ↓
写入 .vault 文件的 fields[].value
```

**Python 实现参考：**

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import base64

def encrypt_field(plaintext: str, session_key: bytes, *,
                  aad: bytes | None) -> str:
    # aad 为 keyword-only 无默认值：v2 传 field_aad(...) 的结果，
    # v1 传 None（AAD 构造见 6.7）
    iv = os.urandom(12)
    aesgcm = AESGCM(session_key)
    ciphertext_with_tag = aesgcm.encrypt(iv, plaintext.encode('utf-8'), aad)
    encoded = base64.b64encode(iv + ciphertext_with_tag).decode('utf-8')
    return "ENC:" + encoded

```

### 6.3 解密单个 secret 字段（显示/复制时触发）

```
.vault 文件中的 "ENC:BASE64STRING"
        ↓
去掉 "ENC:" 前缀
        ↓
base64 解码 → 字节流
        ↓
前12字节 = IV
剩余字节 = 密文 + 认证标签（最后16字节）
        ↓
AES-256-GCM 解密（使用内存中的 session_key）
        ↓
若认证标签验证通过 → 返回明文字符串
若验证失败 → 抛出异常，界面显示"解密失败，请检查密码"
```

**Python 实现参考：**

```python
def decrypt_field(encrypted_value: str, session_key: bytes, *,
                  aad: bytes | None = None) -> str:
    if not encrypted_value.startswith("ENC:"):
        return encrypted_value  # 非加密字段直接返回
    encoded = encrypted_value[4:]
    raw = base64.b64decode(encoded)
    iv = raw[:12]
    ciphertext_with_tag = raw[12:]
    aesgcm = AESGCM(session_key)
    # aad 不匹配（密文被搬到其他 entry/field）同样导致认证失败
    plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, aad)
    return plaintext.decode('utf-8')
```

### 6.4 密码哈希（accounts.conf 中存储）

登录密码和导出密码**不用于加密数据**，只用于验证身份，以哈希方式存储。

```
用户密码
        +
随机 salt（16字节）
        ↓
PBKDF2-HMAC-SHA256，iterations=600000
        ↓
存储格式："pbkdf2:sha256:600000$<salt_hex>$<hash_hex>"
```

**验证时**：从存储字符串解析出 salt 和参数，对输入密码重新计算哈希，与存储哈希比较。

### 6.5 加密注意事项

- 每个 secret 字段每次保存时**独立生成新 IV**，即使值未改变，密文也会不同
- 不同字段使用**相同的 session_key**，但 IV 不同，保证安全
- session_key 存在内存变量中，**从不写入任何文件**
- 锁屏、退出、切换账号时，session_key 必须显式设为 None

### 6.6 手动解密说明（README.txt 内容）

```
TJKEY 灾难恢复说明
==================

如果主程序 TJ-KEY.exe 无法使用，可以用 recover.py 手动解密数据。

要求：安装了 Python 3.11+ 和 cryptography 库
安装 cryptography：pip install cryptography

使用方法：
  python recover.py <vault文件路径>

示例：
  python recover.py "C:\MyVault\vaults\main.vault"

运行后程序会提示输入登录密码，验证通过后将解密结果保存为：
  main_recovered_YYYYMMDD_HHMMSS.json   （完整 JSON，所有字段明文）
  main_recovered_YYYYMMDD_HHMMSS.md     （Markdown 格式，便于阅读）

加密算法：AES-256-GCM
密钥派生：PBKDF2-HMAC-SHA256，60万次迭代
```

### 6.7 AAD 字段位置绑定（version 2）

version 2 起，每个加密字段的 AES-256-GCM 认证除密文外还绑定
附加认证数据（AAD，Additional Authenticated Data）：

```
AAD = b"tjkey-v2|" + entry_id + b"|" + field_id
      （crypto.build_field_aad / recover.build_field_aad_standalone）
```

- **效果**：密文被搬到其他条目/字段位置后，解密时构造的 AAD 与
  加密时不同，认证标签验证失败——防止字段搬移/重排攻击
- **构造入口**：UI 层统一用 `crypto.field_aad(vault_data, entry_id,
  field_id)` 按版本取值——version < 2 返回 `None`（v1 无 AAD
  语义），version ≥ 2 返回 AAD 字节串，缺 ID 直接 `ValueError`
  拒绝不静默降级
- **加密侧**：`encrypt_field(plaintext, key, *, aad)` 为
  keyword-only 无默认值，调用方必须显式声明版本语义
  （v1 传 `aad=None`）；解密侧 `decrypt_field(..., aad=None)`
  默认兼容 v1 密文
- **格式迁移**：`vault_io.migrate_aad_format(path, key,
  target_version)` 做 version 1 ⇄ 2 双向转换（两遍式：
  先全部解密再重新加密，外部修改哈希保护，失败不写盘）。
  登录时 version 1 文件自动升级到 2（见 23.1）；
  vault_admin 菜单 [7] 手动升降级（见 18.6）
- **双实现约束**：`recover.py` 独立分发不依赖 crypto.py，
  内含第二份 `build_field_aad_standalone`——两份实现必须
  逐字节一致，由 `_test_aad_consistency.py` 断言
  （覆盖空 ID / 中文 / Unicode / 缺 ID，见 24.1）

---

## 7. 账户系统

### 7.1 首次启动引导流程

```
程序启动
    ↓
读取 VaultApp/app.config
    ↓
文件不存在 或 路径无效？
    ↓ 是
弹出引导窗口：
  "欢迎使用 TJKEY！
   请选择您的数据文件夹（MyVault）所在位置。
   如果您是第一次使用，请先新建一个空文件夹。"
  [浏览文件夹] 按钮
    ↓ 选择后
检查文件夹内是否有 accounts.conf
    ↓ 没有（全新安装）
提示："未检测到账户配置，请先运行 vault_admin.py 创建您的第一个账号"
打开文件管理器定位到 VaultApp 文件夹
程序退出
    ↓ 有（已有数据，换电脑或重装）
将路径写入 app.config
进入登录界面
```

### 7.2 登录界面

```
┌─────────────────────────────────────┐
│                                     │
│           🔐  TJKEY                 │
│                                     │
│   账号   [main              ]       │
│   密码   [                  ]       │
│                                     │
│            [  登 录  ]              │
│                                     │
│   显示名称会在输入账号后自动更新     │
│                                     │
└─────────────────────────────────────┘
```

**登录逻辑：**
1. 账号输入框默认填入 `app.conf` 中的 `last_account`（首次为 `accounts.conf` 中的 `default_account`）
2. 显示名称查询走内存缓存：窗口创建时读取一次 `accounts.conf` 并预热缓存（username → display_name），此后账号联想的每次按键不再读盘；未命中的账号提示"账号不存在"
3. 点击登录：先验证账号名是否存在，再验证密码哈希（PBKDF2 常量时间比较）
4. 密码验证通过后：
   - 从 vault 文件读取 `kdf_params`（salt 与 iterations），在 **QThread 后台线程**派生 `session_key`（约 0.3-1 秒），期间显示进度条并禁用输入
   - **密钥-数据匹配校验**：派生完成后用 vault 中第一个加密字段实测该密钥能否解密。若密码哈希验证通过但解密失败（accounts.conf 与 vault 文件因云盘同步错位/冲突副本不匹配），拦截登录、清空会话并提示，避免出现"登录成功但所有字段解密失败"的状态
   - 记录 vault 文件内容 SHA-256 到 `session.vault_content_hash`，作为后续保存的外部修改检测基准
   - 将 `last_account` 更新到 `app.conf`
   - 检查云盘冲突文件（见第16节），有冲突时延迟弹出提示
   - 打开主界面

### 7.3 登出与锁屏

**登出：**
- 销毁详情/编辑面板中可能持有明文的控件（字段行 QLabel、解密后的输入框），并清除列表选中状态
- 清除 `session_key`、`vault_data`、`vault_content_hash`（session.lock()）
- 回到登录界面

**锁屏（自动或手动）：**
- 与登出相同，但登录界面预填上次账号名
- 锁屏状态下自动锁屏计时器不再重启：全局事件过滤器在登录界面同样会重置计时器，`_do_lock` 与 `_reset_lock_timer` 均有 `session.is_locked()` 守卫，防止在登录界面重复触发锁屏、叠加新的登录窗口

**自动锁屏计时：**
- 主窗口安装 QApplication 级事件过滤器，鼠标移动/点击/键盘/滚轮任意交互即重置计时器
- 超时时间来自 `app.conf` 的 `auto_lock_minutes`（默认 2 分钟，可在设置中改为 1/2/5/10 分钟或"从不"）

---

## 8. 主程序界面设计

### 8.1 整体布局

```
┌──────────────────────────────────────────────────────────────────┐
│ TJKEY — 大号                               [锁屏] [设置] [导出]  │ ← 顶部标题栏
├──────────────────────────────────────────────────────────────────┤
│ 🔴 到期提醒：有 2 项将在 1 个月内到期  [展开 ▼]                  │ ← 到期提醒折叠条
├──────────────┬───────────────────────────┬───────────────────────┤
│              │  🔍 搜索账号...            │                       │
│  📂 开发工具 │ ─────────────────────────│                       │
│    📁 Google │  Cloudflare 主号          │  条目详情面板          │
│    📁 AI平台 │  ──────────────────────── │                       │
│  📂 域名注册 │  Cloudflare 备号A         │  （点击左侧列表        │
│    📁 CF     │  ──────────────────────── │   条目后显示）         │
│    📁 US.KG  │  US.KG 账号1              │                       │
│  📂 社交媒体 │  ──────────────────────── │                       │
│              │                           │                       │
│  ──────────  │                           │                       │
│  🏷️ 所有条目 │                           │                       │
│  📦 未分类   │                           │                       │
│              │                           │                       │
├──────────────┴───────────────────────────┴───────────────────────┤
│  [+ 新建条目]    主题: [🌙]    共 42 条记录                       │ ← 底部状态栏
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 三栏比例

| 栏位 | 宽度比例 | 最小宽度 |
|---|---|---|
| 左侧分类导航 | 20% | 180px |
| 中间条目列表 | 35% | 280px |
| 右侧详情面板 | 45% | 360px |

三栏均可通过拖拽分隔线调整宽度，调整后的比例**不持久化**（关闭后恢复默认）。

### 8.3 左侧分类导航

**展示内容：**
- 分类树（大类 → 小类，两级，支持折叠）
- 分隔线
- 固定项："🏷️ 所有条目"、"📦 未分类"

**交互：**
- 点击大类：右侧列表显示该大类下所有条目
- 点击小类：右侧列表显示该小类下所有条目
- 点击"所有条目"：显示全部
- 点击"未分类"：显示 category_id 为 null 的条目
- 右键大类/小类：弹出菜单（重命名、删除、新建子类）
- 右键空白区域：弹出菜单（新建大类）

**拖拽排序规则：**
- 大类之间可上下拖拽排序
- 小类可在同一大类内上下拖拽排序
- 小类可拖拽到另一个大类下（改变归属）
- 小类不能拖拽成为另一个小类的子类（严格两级）
- 条目不能在导航栏拖拽（条目排序在列表区完成）
- 拖拽释放后立即保存到 vault 文件

### 8.4 中间条目列表

每个条目显示为一行：

```
┌──────────────────────────────────────┐
│  Cloudflare 主号                      │
│  域名注册 > Cloudflare · 3个域名      │
└──────────────────────────────────────┘
```

- 第一行：条目名称（粗体）
- 第二行：分类路径 + 摘要（如有 date_domain 字段则显示"X个域名"）
- 点击条目：右侧详情面板显示该条目
- 条目之间可上下拖拽排序（仅在同一分类视图下有效）
- 右键条目：弹出菜单（编辑、删除、移动到分类）

### 8.5 顶部标题栏按钮

| 按钮 | 功能 |
|---|---|
| 锁屏 | 清除 session_key，回到登录界面 |
| 设置 | 打开设置面板（主题切换、自动锁屏时间、模板管理） |
| 导出 | 触发二级密码验证流程，通过后导出 Markdown |

---

## 9. 条目模板系统

### 9.1 新建条目流程

```
点击底部"+ 新建条目"
        ↓
弹出模板选择弹窗：
  ┌─────────────────────────┐
  │  选择模板               │
  │                         │
  │  ○ 通用账号             │
  │  ○ 域名账号             │
  │  ○ 开发平台             │
  │  ○ 邮箱账号             │
  │  ○ 金融/支付            │
  │  ─────────────────────  │
  │  ○ Cloudflare 专用      │ ← 自定义模板
  │                         │
  │       [选择] [取消]     │
  └─────────────────────────┘
        ↓ 选择模板后
进入编辑模式（见第13节），字段按模板预填（值为空）
```

### 9.2 模板管理界面（设置页面内）

```
┌─────────────────────────────────────────┐
│  模板管理                               │
├─────────────────────────────────────────┤
│  内置模板（可修改字段，不可删除）        │
│  ○ 通用账号        [编辑字段]           │
│  ○ 域名账号        [编辑字段]           │
│  ...                                    │
├─────────────────────────────────────────┤
│  自定义模板                             │
│  ○ Cloudflare 专用 [编辑字段] [删除]    │
│                                         │
│  [+ 新建自定义模板]                      │
└─────────────────────────────────────────┘
```

**编辑模板字段界面：**
- 显示当前字段列表（label + type）
- 可上下拖拽调整字段顺序
- 可删除字段（内置模板删除字段需二次确认）
- 可添加新字段（输入 label，选择 type）
- 修改后保存到 vault 文件的 templates 节点

---

## 10. 分类与导航系统

### 10.1 新建分类

- 右键导航栏空白区域 → "新建大类" → 输入名称 → 回车确认
- 右键某个大类 → "新建子类" → 输入名称 → 回车确认
- 新建时自动分配 ID（`cat_` + 6位随机字母数字），order 设为当前最大值+1

### 10.2 重命名分类

- 右键分类名 → "重命名" → 输入新名称 → 回车确认
- 或双击分类名进入重命名模式

### 10.3 删除分类

- 右键分类名 → "删除"
- 弹出确认对话框：
  - 若分类下有条目：提示"该分类下有 X 个条目，删除后这些条目将移入「未分类」，确认删除？"
  - 若分类下无条目：直接确认删除
- 删除大类时，其下所有小类也一并删除，条目移入未分类

### 10.4 拖拽排序实现要点

- 使用 PySide6 的 `QTreeWidget` 或自定义 `QListWidget`，开启 `DragDropMode`
- 拖拽结束时（`dropEvent`）立即更新 vault 文件中的 order 值和 category_id 归属
- 拖拽过程中有视觉反馈（高亮目标位置）
- 不允许将大类拖入另一个大类（严格限制两级）

---

## 11. 到期提醒系统

### 11.1 扫描逻辑

登录成功后，扫描当前 vault 文件中所有条目的所有字段：

- `type == "date"` 的字段：value 即为日期字符串 `YYYY-MM-DD`
- `type == "date_domain"` 的字段：value 格式为 `域名名称|YYYY-MM-DD`，取 `|` 后部分作为日期

计算每个日期字段距今天的天数（今天为 D 天，到期日减今天 = 剩余天数）：
- 剩余天数 > 90：绿色
- 30 < 剩余天数 ≤ 90：黄色
- 剩余天数 ≤ 30（包括已过期）：红色

取所有字段中**最紧急的颜色**作为提醒条颜色。

### 11.2 提醒条展示

**折叠状态（默认）：**

```
🟢 到期提醒：所有项目均在 3 个月以外  [▼]
```

```
🟡 到期提醒：有 3 项将在 3 个月内到期  [▼]
```

```
🔴 到期提醒：有 1 项将在 1 个月内到期  [▼]
```

**展开状态（点击后）：**

```
🔴 到期提醒  [▲]
─────────────────────────────────────────────────
🔴  Cloudflare 主号 · 域名2 (mysite.net) · 还有 15 天
🟡  Cloudflare 主号 · 域名1 (example.com) · 还有 62 天
🟡  US.KG 账号1 · 域名 (test.kg) · 还有 88 天
🟢  Namesilo · 域名 (longterm.com) · 还有 210 天
```

展开内容**只显示**：条目名称 + 字段 label（含域名名称）+ 剩余天数。不显示密码、用户名等任何敏感信息。

点击展开列表中的某项，中间列表自动定位到该条目。

### 11.3 已过期处理

- 剩余天数为负数时，显示"已过期 X 天"
- 归入红色类别
- 颜色使用更深的红色以区分"即将到期"和"已过期"

---

## 12. 搜索系统

### 12.1 搜索范围

搜索覆盖以下**明文字段**（不解密 secret 字段）：

| 字段 | 说明 |
|---|---|
| `name` | 条目名称 |
| `url` | 登录网址 |
| `tags` | 标签列表 |
| `category_name` | 所属大类名称（运行时关联） |
| `subcategory_name` | 所属小类名称（运行时关联） |
| `fields[type=text].value` | 所有 text 类型字段的值 |
| `fields[type=text].label` | 所有 text 类型字段的名称 |
| `fields[type=date_domain].value` | 域名部分（`|` 前的内容） |
| `fields[type=date_domain].label` | 字段名称 |
| `fields[type=date].label` | date 字段名称 |
| `fields[type=secret].label` | secret 字段**名称**（不搜索值！） |

### 12.2 搜索交互

- 搜索框位于中间列表区顶部
- 输入时**实时过滤**，无需回车（使用 `textChanged` 信号）
- 搜索词支持空格分隔多关键词（AND 逻辑：所有词都匹配才显示）
- 搜索时忽略左侧分类选中状态（跨全库搜索），搜索框清空后恢复分类筛选
- 搜索结果中关键词高亮显示

### 12.3 搜索性能

所有条目在登录时全量加载到内存（JSON 已解析为 Python 对象），搜索直接在内存中过滤，无 IO 操作，响应速度 < 50ms。

---

## 13. 查看与编辑模式

### 13.1 查看模式（默认）

点击中间列表的条目后，右侧详情面板显示：

```
┌─────────────────────────────────────────────────┐
│  Cloudflare 主号                       [编辑]    │
│  域名注册 > Cloudflare                           │
│  标签：cloudflare  主力                          │
├─────────────────────────────────────────────────┤
│  用户名        admin@gmail.com         [复制]    │
│  密码          ••••••••       [显示]   [复制]    │
│  API Token     ••••••••       [显示]   [复制]    │
│  域名1         example.com | 2026-06-01  [复制]  │
│  域名2         mysite.net  | 2025-11-15  [复制]  │
│  备注          主力账号，绑定信用卡 xxxx  [复制]  │
└─────────────────────────────────────────────────┘
```

**查看模式规则：**
- 所有字段不可点击编辑
- `secret` 字段默认显示为 `••••••••`
- 点击 `[显示]` 按钮：该字段明文显示，按钮变为 `[隐藏]`，点击再次打码
- 点击 `[复制]`：将字段值（明文）写入系统剪贴板
  - `secret` 字段点击复制时自动解密后写入剪贴板，**界面上不显示明文**
  - `date_domain` 字段复制时只复制域名部分（不含到期日）
- 右上角唯一的 `[编辑]` 按钮用于进入编辑模式

### 13.2 编辑模式

点击 `[编辑]` 后，详情面板切换为编辑模式：

```
┌─────────────────────────────────────────────────┐
│  名称  [Cloudflare 主号                 ]        │
│  分类  [域名注册 ▼] > [Cloudflare ▼]            │
│  URL   [https://dash.cloudflare.com     ]        │
│  标签  [cloudflare × ] [主力 ×] [添加+]          │
├─────────────────────────────────────────────────┤
│  用户名    [admin@gmail.com              ]       │
│  密码      [••••••••              ] [显示]        │
│  API Token [••••••••              ] [显示]        │
│  域名1     [example.com] [2026-06-01]  [删除行]  │
│  域名2     [mysite.net ] [2025-11-15]  [删除行]  │
│  备注      [主力账号，绑定信用卡 xxxx    ]        │
│                                                 │
│  [+ 添加字段]                                    │
│                                                 │
│  ─────────────────────────────────────────      │
│  [保存]  [取消]                [删除此条目]      │
└─────────────────────────────────────────────────┘
```

**编辑模式规则：**
- 所有字段变为可编辑输入框
- `secret` 字段编辑框默认打码，旁边有 `[显示]` 按钮
- `date_domain` 字段显示为两个输入框：左边域名（text），右边日期（date picker 或文本输入 YYYY-MM-DD）
- 点击 `[+ 添加字段]`：弹出小弹窗，输入字段名称，选择字段类型，确认后添加到底部
- 点击字段行的 `[删除行]`：立即从编辑界面移除该行（未保存）
- 点击 `[保存]`：
  1. 验证名称不为空
  2. 对所有已修改的 secret 字段重新加密
  3. 将整个条目写入内存缓存，同时写入 vault 文件
  4. 切换回查看模式
- 点击 `[取消]`：丢弃所有修改，切换回查看模式
- 点击 `[删除此条目]`：弹出确认对话框，确认后删除条目，清空右侧详情面板

### 13.3 保存时的加密流程

保存时对 `fields` 数组逐一处理：

```python
for field in entry['fields']:
    if field['type'] == 'secret':
        if field['value_changed']:  # 用户修改过该字段
            field['value'] = encrypt_field(field['plaintext_buffer'], session_key)
            field['plaintext_buffer'] = None  # 立即清除内存中的明文
        # 若未修改，保留原来的 ENC: 值不变
    else:
        field['value'] = field['input_value']  # 直接存明文
```

### 13.4 字段显示顺序

编辑模式下支持上下拖拽调整字段顺序，顺序保存在 `fields[].order` 中。

---

## 14. 导出系统

### 14.1 导出触发流程

```
点击顶部 [导出] 按钮
        ↓
弹出二级密码验证弹窗：
  "请输入导出密码以继续"
  [密码输入框]
  [确认] [取消]
        ↓ 验证 accounts.conf 中的 export_password_hash
        ↓ 失败：提示"密码错误"，关闭弹窗
        ↓ 成功
弹出文件保存对话框（默认文件名 main_export_YYYYMMDD.md）
        ↓ 选择路径后
生成并写入 .md 文件
        ↓
弹出提示："导出成功！文件已保存到 [路径]"
提示包含警告："此文件包含所有明文密码，请妥善保管"
```

### 14.2 导出的 Markdown 格式

```markdown
# 开发工具

## Google 系

### Google 主账号

| 字段 | 值 |
|------|-----|
| 网址 | https://google.com |
| 用户名 | myname@gmail.com |
| 标签 | google, 主力 |

**密码**

```
MyPassword123!
```

**AI Studio API Key**

```
AIzaSyXXXXXXXXXXXXX
```

**备注**

主账号，绑定手机 138xxxx

---

## AI 平台

### OpenRouter

| 字段 | 值 |
|------|-----|
| 网址 | https://openrouter.ai |
| 用户名 | myname@gmail.com |

**密码**

```
MyPassword456!
```

**API Key**

```
sk-or-XXXXXXXXXXXXXXXXXX
```

---

# 域名注册

## Cloudflare

### Cloudflare 主号

| 字段 | 值 |
|------|-----|
| 网址 | https://dash.cloudflare.com |
| 用户名 | admin@gmail.com |
| 域名1 | example.com（到期：2026-06-01） |
| 域名2 | mysite.net（到期：2025-11-15） |

**密码**

```
MyPassword789!
```

**API Token**

```
XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

---

# 未分类

### 某本地软件序列号

...
```

**格式规则：**
- 大类用 `#`，小类用 `##`，条目名用 `###`
- 非 secret 的 text/date/date_domain 字段放在表格中
- 每个 secret 字段单独成一块：`**字段名**` + 代码块
- 代码块使用三反引号，Markdown 渲染后显示一键复制按钮
- 条目之间用 `---` 水平分隔线
- 文件顶部附加导出时间和账号名注释

---

## 15. 自动锁屏

### 15.1 计时逻辑

使用 PySide6 的单次 `QTimer` 实现（主窗口持有）：

- 登录成功后启动计时器，时长为 `app.conf` 中的 `auto_lock_minutes * 60` 秒
- 主窗口在 QApplication 上安装全局事件过滤器，以下任意操作发生时**重置计时器**：
  - 鼠标移动 / 鼠标点击
  - 键盘按键
  - 滚动操作
- 计时器到时触发锁屏：销毁面板明文控件、清除 session_key，切换到登录界面
- `auto_lock_minutes` 为 0 时禁用自动锁屏
- 锁屏状态下计时器不再重启、锁屏动作不再重复触发（防止在登录界面
  叠加新的登录窗口，见第 23.3 节）

### 15.2 配置入口

在设置页面提供调整：
- 下拉选择：1分钟 / 2分钟（默认）/ 5分钟 / 10分钟 / 从不
- 修改后立即生效并保存到 `app.conf`

---

## 16. 云盘冲突检测

### 16.1 冲突文件识别

不同云盘服务在同步冲突时生成的副本文件名规律：

| 云盘服务 | 冲突文件名示例 |
|---|---|
| Dropbox | `main (冲突副本 2025-01-01).vault` |
| OneDrive | `main-PC名.vault` |
| 坚果云 | `main (坚果云冲突 2025-01-01).vault` |
| 百度云盘 | `main (百度云同步冲突).vault` |

检测规则：扫描 `vaults/` 目录，查找文件名包含当前 vault 文件名基础名（去掉 .vault 后缀）且不完全相同的 .vault 文件。

### 16.2 检测时机

- 登录成功后立即检测
- 每次保存 vault 文件后检测

### 16.3 提示弹窗

```
┌─────────────────────────────────────────────────┐
│  ⚠️  检测到云盘冲突文件                          │
│                                                 │
│  以下文件可能是云盘同步产生的冲突副本：           │
│                                                 │
│  · main (冲突副本 2025-06-01).vault             │
│                                                 │
│  建议您：                                       │
│  1. 先备份当前 vaults/ 文件夹                   │
│  2. 手动比较两个文件的内容                      │
│  3. 确认无误后删除冲突副本                       │
│                                                 │
│  [打开文件夹]            [稍后处理]              │
└─────────────────────────────────────────────────┘
```

- 点击"打开文件夹"：用系统文件管理器打开 `vaults/` 目录
- 点击"稍后处理"：关闭弹窗，继续使用程序
- 检测到冲突时，状态栏显示 ⚠️ 警告图标，提醒用户未处理的冲突

---

## 17. 主题系统

### 17.1 主题切换

- 支持"深色"和"浅色"两个主题
- 切换入口：底部状态栏的主题按钮（🌙 深色 / ☀️ 浅色）
- 切换后**立即生效**，无需重启
- 偏好保存到 `app.conf` 的 `theme` 字段

### 17.2 颜色方案（参考值）

**深色主题：**

| 元素 | 颜色 |
|---|---|
| 主背景 | `#1e1e2e` |
| 侧边栏背景 | `#181825` |
| 卡片/面板背景 | `#313244` |
| 主文字 | `#cdd6f4` |
| 次要文字 | `#a6adc8` |
| 强调色 | `#89b4fa` |
| 危险色 | `#f38ba8` |
| 警告色 | `#f9e2af` |
| 成功色 | `#a6e3a1` |
| 边框 | `#45475a` |

**浅色主题：**

| 元素 | 颜色 |
|---|---|
| 主背景 | `#eff1f5` |
| 侧边栏背景 | `#e6e9ef` |
| 卡片/面板背景 | `#ffffff` |
| 主文字 | `#4c4f69` |
| 次要文字 | `#6c6f85` |
| 强调色 | `#1e66f5` |
| 危险色 | `#d20f39` |
| 警告色 | `#df8e1d` |
| 成功色 | `#40a02b` |
| 边框 | `#ccd0da` |

### 17.3 PySide6 主题实现方式

使用 Qt StyleSheet（QSS）实现主题，定义两套 QSS 字符串，切换时调用 `app.setStyleSheet(theme_qss)`。

---

## 18. vault_admin.py 管理脚本

### 18.1 功能范围

- 创建新账号
- 修改账号的登录密码
- 修改账号的导出密码
- 修改账号显示名称 / 设置默认账号
- 删除账号
- 升级/降级数据文件格式（version 1 ⇄ 2，见 18.6）
- 查看所有账号列表

### 18.2 运行方式

```bash
# 在 VaultApp 目录下双击运行，或命令行执行：
python vault_admin.py
```

### 18.3 交互界面（命令行菜单）

```
  TJKEY  账户管理工具
────────────────────────────────────────────────
当前账号：
    · main（大号）[默认]
    · sub1（小号1）

请选择操作：
  [1] 创建新账号
  [2] 修改登录密码
  [3] 修改导出密码
  [4] 修改账号显示名称
  [5] 设置默认登录账号
  [6] 删除账号
  [7] 升级/降级数据文件格式
  [0] 退出
────────────────────────────────────────────────
请输入选项：
```

### 18.4 创建账号流程

```
请输入新账号的用户名（仅字母数字下划线，如 sub2）：sub2
请输入显示名称（如 小号2）：小号2
请输入登录密码：****
请再次输入登录密码（确认）：****
请输入导出密码（用于导出明文，可与登录密码不同）：****
请再次输入导出密码（确认）：****

正在创建账号...
✓ 账号 sub2 创建成功
✓ 已生成 vaults/sub2.vault（空白数据文件）
✓ 已更新 accounts.conf
```

**创建时的操作：**
1. 验证 username 格式（正则：`^[a-zA-Z0-9_]+$`）
2. 验证 username 在 accounts.conf 中唯一
3. 对登录密码和导出密码分别生成 PBKDF2 哈希
4. 创建空白的 `.vault` 文件，生成新的 kdf salt
5. 写入 `accounts.conf`

### 18.5 删除账号流程

```
请输入要删除的账号用户名：sub2
警告：此操作将删除账号 sub2（小号2）及其所有数据！
请输入该账号的登录密码以确认：****
请输入"确认删除"以继续：确认删除

正在删除账号...
✓ 已删除 vaults/sub2.vault
✓ 已从 accounts.conf 移除账号 sub2
```

删除时需验证登录密码，防止误操作。

### 18.6 升级/降级数据文件格式（菜单 [7]）

version 1 ⇄ 2 的手动双向转换，是登录自动升版（见 23.1）的
补充与**回退通道**：

```
请选择操作：
  [7] 升级/降级数据文件格式
请输入选项：7
请输入账号用户名：main
-> 账号 main 当前为 version 2，将降级到 version 1（供回退旧版程序）
[!] 转换会重写整个数据文件，期间请勿断电！
[!] 请先完全退出 TJKEY 主程序，否则可能造成数据不一致！
继续吗？(y/N)：y
请输入该账号的登录密码以确认身份：****

[OK] 已迁移到 version 1，转换 16 个加密字段
[!] 降级为旧格式：请改用旧版程序打开；新版程序登录时会再自动升级到 version 2。
```

**行为要点：**

- 自动判定方向：当前 version 2 → 降级到 1；当前 version 1 → 升级到 2
- 需验证登录密码；转换实现为 `vault_io.migrate_aad_format`
  （两遍式 + 外部修改哈希保护，任一字段失败不写盘，无半迁移文件）
- 幂等：已是目标版本时返回 0、不写盘
- **回退路径**：旧版程序不认 version 2。回退前先在新版用菜单 [7]
  降级，再换旧版程序；否则旧版会报"不支持的 Vault 文件版本"
- **云同步警告**：多机共享 MyVault 时，升降级都会重写文件并触发
  同步——必须所有机器先升级程序，再打开数据文件

---

## 19. recover.py 灾难恢复脚本

### 19.1 设计原则

- **零外部依赖**：只使用 Python 标准库 + `cryptography` 库（仅此一个依赖）
- **不依赖 PySide6**：纯命令行，任何装了 Python 的电脑都能运行
- **输出两种格式**：JSON（完整数据）+ Markdown（可读文档）
- **双版本兼容**：按文件 `version` 自动选择 AAD 语义——version 1
  无 AAD 解密，version 2 用本地复制的 `build_field_aad_standalone`
  构造 AAD（不 import crypto.py，dist 分发包不含它）；version > 2
  明确拒绝退出（更新版程序创建的文件，提示先升级 recover.py）。
  两份 AAD 实现由 `_test_aad_consistency.py` 断言逐字节一致

### 19.2 运行方式

```bash
python recover.py <vault文件路径>

# 示例
python recover.py "C:\MyVault\vaults\main.vault"
```

### 19.3 执行流程

```
读取指定 vault 文件
        ↓
显示账号信息和 kdf_params
        ↓
提示输入登录密码
        ↓
派生 session_key
        ↓
尝试解密第一个 secret 字段验证密码正确性
  失败 → 提示"密码错误"，退出
  成功 → 继续
        ↓
解密所有 ENC: 字段
        ↓
输出文件1：main_recovered_20250101_120000.json（所有字段明文）
输出文件2：main_recovered_20250101_120000.md（Markdown 格式）
        ↓
提示成功，显示输出文件路径
```

### 19.4 输出的 JSON 格式

与 vault 文件结构相同，但所有 `ENC:` 值替换为解密后的明文字符串，`kdf_params` 保留。

---

## 20. 打包配置

### 20.1 使用 build.spec 打包（推荐）

```bash
pip install "pyinstaller>=6.0"
pyinstaller build.spec --noconfirm
```

- 输出：`dist/TJ-KEY/TJ-KEY.exe` + `dist/TJ-KEY/_internal/`（onedir 模式）。
- spec 已适配 PyInstaller 6.x（移除了 5.x 的 `block_cipher`/`cipher`/
  `win_no_prefer_redirects`/`win_private_assemblies` 参数）。
- 打包完成后 `build/` 为中间产物，可删除；`dist/` 即发布目录。
- 冒烟验证：双击 `TJ-KEY.exe`（无 app.config 时应弹出首次设置向导）。

### 20.2 主要参数说明（build.spec）

| 配置 | 说明 |
|---|---|
| `name='TJ-KEY'` | 输出的 exe 名称为 TJ-KEY.exe |
| `exclude_binaries=True` + `COLLECT` | onedir 模式，启动速度快于 onefile |
| `console=False` | 不显示命令行黑窗口 |
| `upx=False` | 不用 UPX 压缩（避免杀软误报） |
| `datas=[assets]` | 图标资源打包进 `_internal/assets` |
| `hiddenimports` | PySide6 / cryptography 的子模块显式声明 |

### 20.3 不打包的文件

`vault_admin.py` 和 `recover.py` 直接作为 `.py` 文件发布（与 exe 同目录），不打包进 exe。用户需要安装 Python 才能运行（但通常这类文件只在需要时才用，不影响日常使用）。

### 20.4 最终发布结构

```
📁 VaultApp/
    📄 TJ-KEY.exe
    📄 vault_admin.py
    📄 recover.py
    📄 markdown_export.py   ← recover.py 的共享模块，需同目录
                            （三者由 build.spec 打包时自动复制到位）
    📄 app.config          ← 首次启动后自动生成
    📁 _internal/
        ... (依赖文件，PyInstaller 6 起依赖集中于此)
```

---

## 21. 开发顺序建议

建议按以下顺序开发，每个阶段都能独立测试：

### 阶段一：数据层（无界面）
1. `crypto.py`：加密/解密/密钥派生函数
2. `vault_io.py`：vault 文件读写、JSON 序列化
3. `accounts.py`：accounts.conf 读写、密码验证
4. 单元测试：加密→保存→读取→解密的完整循环

### 阶段二：管理脚本
5. `vault_admin.py`：命令行账户管理工具
6. `recover.py`：灾难恢复脚本
7. 测试：创建账号，写入测试数据，用 recover.py 恢复

### 阶段三：主界面框架
8. `main.py`：程序入口，首次启动引导
9. `ui/login.py`：登录界面
10. `ui/main_window.py`：主窗口三栏布局
11. 主题系统 QSS

### 阶段四：核心功能
12. `ui/nav_panel.py`：左侧分类导航（含拖拽）
13. `ui/entry_list.py`：中间条目列表
14. `ui/entry_detail.py`：右侧详情面板（查看模式）
15. `ui/entry_edit.py`：编辑模式

### 阶段五：扩展功能
16. `ui/expiry_bar.py`：到期提醒折叠条
17. 搜索功能
18. 模板系统
19. `ui/export.py`：导出功能

### 阶段六：收尾
20. 自动锁屏计时器
21. 云盘冲突检测
22. 设置页面
23. PyInstaller 打包配置
24. 完整功能测试

---

## 22. 各模块接口约定

### 22.1 数据层接口

```python
# crypto.py
def generate_salt() -> str: ...
def derive_key(password: str, salt_b64: str,
               iterations: int = 600000) -> bytes: ...
# iterations 应传 vault 文件 kdf_params.iterations 中记录的值；
# 非法值（非整数 / 超出 1..10_000_000）抛 ValueError
def build_field_aad(entry_id: str, field_id: str) -> bytes: ...
#    AAD = b"tjkey-v2|" + entry_id + b"|" + field_id；
#    空/缺 ID 抛 ValueError（version 2 防呆）
def field_aad(vault_data: dict, entry_id, field_id) -> bytes | None: ...
#    version < 2 → None；version ≥ 2 → build_field_aad(...)（缺 ID 抛 ValueError）
def encrypt_field(plaintext: str, key: bytes, *,
                  aad: bytes | None) -> str: ...
#    keyword-only 无默认值，调用方显式声明版本语义（v1 传 aad=None）
def decrypt_field(encrypted: str, key: bytes, *,
                  aad: bytes | None = None) -> str: ...
#    非加密字段（无 ENC: 前缀）原样返回；解密失败抛 DecryptError
#    （含 AAD 不匹配——密文被搬到其他 entry/field 位置）
def is_encrypted(value: str) -> bool: ...
def hash_password(password: str) -> str: ...
def verify_password(password: str, hash_str: str) -> bool: ...
#    畸形/被篡改的哈希串一律返回 False，绝不抛异常

# vault_io.py
def load_vault(vault_path: str) -> dict: ...
#    格式错误抛 VaultFormatError，文件缺失抛 FileNotFoundError；
#    version 只接受 1 和 2，其他值拒绝
def save_vault(vault_path: str, data: dict,
               expected_hash: str | None = None) -> None: ...
#    tmp + fsync + 原子替换；expected_hash 与磁盘内容不符时
#    抛 VaultExternallyModifiedError（外部修改检测，见第 23 章）
def save_vault_checked(vault_path, data, known_hash) -> str | None: ...
#    带检测的保存，成功后返回新的内容哈希（供 UI 层更新基准）
def file_sha256(path: str) -> str | None: ...
def find_first_encrypted_field(data: dict) -> tuple | None: ...
#    返回 (entry_id, field_id, value) 三元组，供登录校验构造 AAD；
#    跳过回收站（deleted）条目
def migrate_aad_format(vault_path: str, session_key: bytes, *,
                       target_version: int = 2) -> int: ...
#    version 1 ⇄ 2 双向迁移；两遍式 + expected_hash，失败不写盘；
#    已是目标版本返回 0（幂等不写盘）。登录自动升版与菜单 [7] 共用
def reencrypt_vault_password(vault_path, old_password, new_password) -> int: ...
#    修改登录密码时的两遍式重加密；中断后重试可自愈；
#    保持源文件 version 不变（v1 改密后仍为 v1，登录时才升版）
def create_empty_vault(vault_path: str, account: str) -> dict: ...
#    新建文件直接生成 version 2
def reorder_categories(data: dict, new_order: list) -> None: ...
#    new_order 遗漏的 ID 追加到末尾，不会被丢弃

# recover.py（独立实现，不 import crypto/vault_io）
def build_field_aad_standalone(entry_id, field_id) -> bytes: ...
def field_aad_for(version, entry_id, field_id) -> bytes | None: ...
def decrypt_field_standalone(encrypted_value: str, key: bytes,
                             aad: bytes | None = None) -> str: ...
#    与 crypto.py 的 AAD 构造必须逐字节一致（_test_aad_consistency.py 断言）

# ui/vault_sync.py —— UI 层统一保存入口（所有面板保存都走这里）
def save_vault_or_lock() -> bool: ...
#    成功返回 True；文件被外部修改→弹窗提示并强制锁屏回登录；
#    写盘失败（IOError）→弹窗提示；两种失败均已处理，不向外抛异常

# accounts.py
def load_accounts(myVault_path: str) -> dict: ...
def get_account(accounts: dict, username: str) -> dict | None: ...
def verify_login(accounts: dict, username: str, password: str) -> bool: ...
def verify_export_password(accounts: dict, username: str, export_password: str) -> bool: ...
def change_password(myVault_path, username, old_password, new_password) -> bool: ...
#    先重加密 vault 再更新哈希；中途断电重试同一命令可自愈
def delete_account(myVault_path: str, username: str, password: str) -> bool: ...
def get_vault_path(myVault_path: str, accounts_data: dict, username: str) -> str: ...
#    含路径穿越防护：vault_file 解析结果指向 MyVault 之外时返回 ""
```

### 22.2 全局状态（session）

```python
# session.py — 运行时全局状态
class Session:
    myVault_path: str = ""                      # MyVault 数据文件夹路径
    current_account: str = ""                   # 当前登录账号 username
    current_display_name: str = ""              # 当前账号显示名称
    session_key: bytes | None = None            # 派生的 AES-256 密钥，永不落盘
    vault_data: dict | None = None              # 当前 vault 的内存快照
    vault_path: str = ""                        # 当前 vault 文件绝对路径
    vault_content_hash: str | None = None       # 保存时的外部修改检测基准
    main_window = None                          # 主窗口引用（锁屏信号用）

    def lock(self):
        # 清除密钥与敏感数据；保留 myVault_path 与 main_window
        self.session_key = None
        self.vault_data = None
        self.current_account = ""
        self.current_display_name = ""
        self.vault_path = ""
        self.vault_content_hash = None

    def is_locked(self) -> bool:
        return self.session_key is None
```

### 22.3 UI 信号约定

```python
# 常用信号
entry_selected = Signal(str)            # 条目ID，触发详情面板更新
entry_saved = Signal(str)               # 条目ID（edit 面板名 save_done）
entry_deleted = Signal(str)             # 条目ID，触发列表刷新
cancel_requested = Signal()             # 编辑面板取消，切回查看模式
category_selected = Signal(str, object) # (cat_id, sub_id)，导航选中
categories_changed = Signal()           # 分类结构变化，触发导航/列表刷新
login_success = Signal()                # 登录完全成功（密钥已派生并校验）
lock_requested = Signal()               # 请求锁屏（主窗口 → main.py）
new_entry_requested = Signal(str, object, object)  # (tpl_id, cat_id, sub_id)
```

**保存链路约定：** 所有 UI 面板保存 vault 一律调用
`ui/vault_sync.save_vault_or_lock()`，禁止直接调用
`vault_io.save_vault`——前者带外部修改检测与强制锁屏（见第 23 章 P2-1）。

---

## 23. 代码审查与安全加固记录

2026 年 9 月对全部源码做了三轮代码审查与修复（P1 严重 / P2 重要 / P3 优化），
每轮修复都有对应的离屏验证脚本（见第 24 章），修复后的行为以脚本断言为准。
以下按主题归纳各机制的最终实现。

### 23.1 登录链路

| 机制 | 位置 | 说明 |
|---|---|---|
| 密钥-数据匹配校验 | `ui/login.py` `_on_derive_finished` | 密码哈希验证通过后，用 vault 中第一个 ENC: 字段实测派生密钥能否解密（version 2 按 `field_aad` 构造 AAD）；失败（云盘同步错位/冲突副本）拦截登录并清空会话 |
| 登录自动升版 v1 → v2 | `ui/login.py` `_on_derive_finished` → `vault_io.migrate_aad_format` | 校验通过且文件为 version 1 时原地迁移到 version 2（两遍式 + 哈希保护，失败不写盘）；任何失败静默降级为本次按 v1 使用、下次登录重试，不阻断登录；无论成败都重读磁盘刷新 `vault_data` 与 `vault_content_hash`（重读失败则旧哈希会在下次保存触发外部修改检测强制锁屏，宁锁不写脏数据）。回退旧版程序用菜单 [7] 降级（见 18.6） |
| 迭代次数以文件为准 | `crypto.derive_key` / `ui/login.py` / `vault_io.reencrypt_vault_password` | 登录与重加密均按 `kdf_params.iterations` 派生，非法值（非整数、超出 1..10,000,000）拒绝；未来上调迭代次数后旧 vault 仍可登录，且与 recover.py 行为一致 |
| 密码验证参数白名单 | `crypto.verify_password` | 算法/哈希名白名单 + 迭代次数上限 + 全异常按"验证失败"处理，畸形 accounts.conf 不会让登录崩溃 |
| 后台派生 | `ui/login.py` `DeriveKeyWorker`（QThread） | PBKDF2 约 0.3-1 秒，后台线程执行避免 UI 卡顿 |

### 23.2 保存链路（外部修改检测）

背景：主程序把整个 vault 快照放在内存里，任何保存都是整体写回。
若 vault_admin 在主程序运行期间用新密码重加密了 vault（或云盘同步拉取了
远端版本），主程序的下一次保存会用旧密钥的密文覆盖磁盘，之后所有加密
字段都无法解密。为此：

- `vault_io.save_vault` 新增 `expected_hash` 参数：写盘前比对磁盘文件内容的
  SHA-256，与调用方已知基准不符时抛 `VaultExternallyModifiedError`，拒绝写入；
- `session.vault_content_hash` 在登录加载与每次成功保存后更新，作为检测基准；
- `ui/vault_sync.save_vault_or_lock()` 是 UI 层唯一保存入口：检测到外部修改时
  弹窗说明并**强制锁屏回登录界面**（丢弃过期内存快照，重新登录即加载磁盘
  最新数据）；写盘失败（磁盘满等）单独弹窗提示；
- `reencrypt_vault_password` 内部保存同样携带加载时的内容哈希，防止
  改密过程中文件被云盘覆盖（TOCTOU）；
- `vault_admin.py` 修改密码时仍会警告"请先关闭主程序"，但即使忘记关闭，
  主程序的后续保存也会被拦截，不会造成数据损坏。

### 23.3 锁屏与剪贴板

| 机制 | 位置 | 说明 |
|---|---|---|
| 锁屏计时器守卫 | `ui/main_window.py` `_do_lock` / `_reset_lock_timer` | 已锁屏时不再重启计时器、不再发射 `lock_requested`——否则登录界面闲置超时会叠加新的登录窗口 |
| 面板明文清理 | `ui/main_window.py` `_do_lock` / `on_login`；`ui/entry_edit.py` | 锁屏/重新登录销毁详情、编辑面板的明文控件；编辑面板保存/删除成功后立即 `clear()` |
| 剪贴板自动清空 | `ui/entry_detail.py` | 复制（含 URL 复制）30 秒后自动清空剪贴板；使用**应用级** `QTimer.singleShot` + 模块级 `_clear_clipboard_if_matches`，字段行销毁（切换条目/锁屏）不影响清空；仅当剪贴板内容仍是刚复制的值时才清空，不覆盖用户后续复制 |

### 23.4 输入与导出防护

- **URL 打开白名单**：`ui/entry_detail.py` `_open_url` 用 `urlparse` 做严格
  scheme 解析，仅放行 http/https（`javascript:` 这类无 `//` 的协议同样拦截）；
  裸域名自动补 `https://` 后打开。
- **ENC: 二次加密拦截**：编辑面板保存时拒绝以 `ENC:` 开头的 secret 输入
  （解密失败的字段进入编辑时已清空），防止密文被再加密一层。
- **日期格式校验**：`date` 与 `date_domain` 字段保存前校验 `YYYY-MM-DD`，
  非法日期拦截保存（否则会被到期扫描静默跳过）。
- **Markdown 导出加固**：secret 值含 ``` 时围栏自动加长；表格单元格
  （标签与值）竖线转义；孤儿分类条目归入"未分类"，不再丢失；
  GUI 导出与 recover.py 输出逐字一致（共享 `markdown_export.build_markdown`）。
- **recover.py 防护**：派生函数拒绝畸形 `iterations` 与缺失 `salt`，
  迭代次数上限与 crypto.py 保持一致。

### 23.5 数据健壮性

- `accounts.load_app_conf` 返回深拷贝，嵌套默认配置（如 window_geometry）
  不被调用方的原地修改污染。
- `reorder_categories` / `reorder_subcategories` 对遗漏/重复 ID 追加末尾
  并重排 order，分类数据不再因调用方传错顺序而丢失。
- 登录界面显示名称走内存缓存（窗口创建时预热一次），账号联想不再逐键读盘。
- 死代码清理：移除未被引用的 `ui/expiry_bar.py`（main_window 已有等价
  内联实现）及各 UI 模块未使用的 imports。
- `requirements.txt` 增加版本上限；新增 `.gitignore`（app.config 含个人
  路径，禁止入库）。

---

## 24. 测试与验证

项目采用"模块自测 + 分轮修复验证脚本"两层验证，均为标准 Python 脚本，
无需 pytest 或额外依赖。

### 24.1 运行方式

```bash
# ── 数据层模块自测（无窗口依赖）
python crypto.py        # 加密/解密/哈希/畸形输入/AAD 构造
python vault_io.py      # vault 读写/CRUD/重加密/冲突检测/格式迁移
python accounts.py      # 账户/改密/自愈/路径穿越防护

# ── 分轮修复验证（自动离屏运行，QT_QPA_PLATFORM=offscreen 已内置）
python _test_aad_consistency.py  # AAD 双实现（crypto/recover）逐字节一致
python _test_p1_fixes.py     # P1：登录/锁屏/编辑面板安全修复
python _test_p2_fixes.py     # P2：外部修改检测/迭代次数/URL 协议
python _test_p3_fixes.py     # P3 第一轮：导出统一/剪贴板/引导流程
python _test_p3_round2.py    # P3 第二轮：配置深拷贝/导出加固/日期校验
python _test_p4_features.py  # P4：密码生成器/应用内改密/引导建号/回收站
python _test_p5_reliability.py  # P5：单实例锁/系统锁屏联动/滚动备份
python _test_e2e_full.py     # 全流程端到端（10 阶段用户旅程，见 24.3）

# ── pytest 一键运行（子进程隔离，CI 使用同一入口）
python -m pytest tests       # 全部脚本一次跑完，约 20 秒

# ── 真实数据迁移试运行（人工执行，只读源目录、不进自动化清单）
python tools_trial_migration.py --myvault D:\MyVault  # myaccount.vault 副本上 v1→v2→v1 双向试运行
```

### 24.2 通过标准与回归要求

- 每个脚本运行结束输出 `=== ... 验证通过 ===` 即代表全部断言通过。
- 修改 `crypto.py` / `vault_io.py` / `accounts.py` 任一核心模块后，
  必须跑完上述全部脚本再交付（`python -m pytest tests` 一条命令即可）。
- `tests/test_suites.py` 以子进程逐个运行全部脚本并断言退出码——
  各脚本内部创建独立临时环境与 QApplication，必须进程级隔离；
  GitHub Actions（.github/workflows/tests.yml）在 Windows/Linux
  双平台执行同一入口。
- 各验证脚本覆盖的具体行为清单见各脚本头部注释。

### 24.3 全流程端到端测试（_test_e2e_full.py）

以离屏方式驱动真实界面类，按完整用户旅程分 10 个阶段：
首次向导建号 → 真实登录（后台派生密钥）→ 建分类/模板条目（密码生成器、
加密落盘校验）→ 搜索/到期/计数 → 模板管理增改 → 回收站全链路 →
GUI 二级密码导出（内容校验）→ recover 灾难恢复 → 应用内改密 + 新密码
重登 → 锁屏清理。

- 曾由此测试抓出真实缺陷：条目列表刷新逻辑缩进错位导致"搜索结果被
  分类视图覆盖、分类视图下搜索崩溃"（已修复并保留断言）。
- 应用当前**没有导入功能**（无任何导入入口），导出侧覆盖 GUI 导出与
  recover 全量恢复两条路径。
- 测试全程使用独立临时目录，绝不触碰本机 app.config 与真实 MyVault。

---

## 25. 功能补全记录（P4）

2026-09-08 补齐代码审查中识别的四个功能缺口，验证脚本为
`_test_p4_features.py`。

### 25.1 密码生成器

- `crypto.generate_password(length, upper, digits, symbols, avoid_ambiguous)`：
  `secrets`（CSPRNG）无偏差采样；启用的字符类保证至少出现一个
  （先随机放置再 Fisher-Yates 洗牌）；长度 8..128；小写字母始终包含；
  `avoid_ambiguous=True` 排除易混淆字符（0/O/o、1/l/I）。
- UI：编辑面板每个 secret 字段行新增生成按钮（钥匙图标），弹出
  `_PasswordGeneratorDialog`（长度、字符类、易混淆选项实时联动，
  可"换一个"、可复制、确认后回填输入框）。

### 25.2 应用内修改登录密码

- 新增 `ui/change_password_dialog.py`：设置对话框 →「登录密码 →」入口。
- 流程：验证当前密码（单独提示，与 vault_admin 体验一致）→ 新密码
  至少 8 位、两次一致、不得与旧密码相同 → `accounts.change_password()`
  （两遍式重加密，中断自愈，见 18.4/23.2）。
- 成功后：当前会话密钥已随重加密作废，对话框自动关闭设置并触发
  主窗口 `_do_lock()` 强制回登录界面，用新密码重新登录。
- 错误分支（旧密码错误、两次不一致等）不改动任何数据。

### 25.3 首次引导建号

- `SetupWizard` 选中空文件夹（无 accounts.conf）时显示
  「创建第一个账号」按钮，弹出 `_CreateAccountDialog` 表单：
  用户名（字母/数字/下划线）、显示名称、登录密码与导出密码（各至少
  8 位、两次一致）。
- 创建内容等价于 vault_admin.py 的建号菜单：注册账号 + 空白 vault
  数据文件 + MyVault/README.txt。
- 创建成功后向导自动刷新状态并启用「确认并开始使用」，新用户无需
  再访问命令行。
- 表单校验：重复用户名、非法字符、密码过短、两次不一致均拒绝且不产生
  半成品数据（vault 文件创建失败时提示用 vault_admin 修复，账号注册
  保留）。

### 25.4 回收站（软删除）

- 数据层（vault_io.py）：
  - `delete_entry` 改为软删除：打 `deleted: true` + `deleted_at` 标记，
    数据不离开 vault 文件；
  - `restore_entry`（恢复）、`purge_entry`（永久删除）、
    `get_deleted_entries`（回收站列表，按删除时间降序）、
    `count_active_entries`（活跃条目计数）；
  - **全口径过滤**：`get_entries_by_category`、`search_entries`、
    `scan_expiry`（到期提醒）、`find_first_encrypted_value`（登录密钥
    校验）均排除已删除条目；`update_entry` 保留回收站标记（编辑
    已删除条目不会使其复活）；
  - **重加密不受影响**：`reencrypt_vault_password` 处理所有加密字段
    （含回收站条目），否则它们在改密后将永久无法解密。
- UI：
  - 左侧导航新增「回收站」固定入口；回收站视图卡片显示删除时间，
    右键菜单为「恢复 / 永久删除」，禁用拖拽排序与新建条目；
  - 普通视图的删除确认文案改为"移入回收站（可恢复）"；
  - 状态栏计数只统计活跃条目。
- 导出区分：程序内导出（`build_markdown` 默认）不包含回收站条目；
  recover.py 灾难恢复传 `include_deleted=True` 全量导出，不丢任何数据。

---

## 26. 可靠性增强记录（P5）

2026-09-08 完成第二档可靠性增强，验证脚本为 `_test_p5_reliability.py`。

### 26.1 单实例锁

- `main.py` 启动时在程序目录创建 `tjkey.lock`（Qt `QLockFile`）：
  已有实例在运行时弹窗提示"已在运行"并退出，`tryLock(0)` 立即返回不阻塞。
- 崩溃残留的锁文件由 QLockFile 的 PID 检测自动识别为陈旧锁并接管。
- 意义：双开时第二实例的保存会被外部修改检测拦截（不损坏数据，见
  23.2），但会反复弹窗强制回登录，体验混乱；单实例锁直接杜绝该场景。

### 26.2 系统锁屏联动

- 新增 `system_lock.py`：`SystemLockWatcher` 以 3 秒间隔通过
  `OpenInputDesktop`（Win32 API）探测会话是否锁定——锁定时系统切换到
  Winlogon 桌面，该调用返回 NULL。探测失败按"未锁定"处理，不影响使用。
- 只在"未锁定→锁定"翻转沿发射一次 `locked` 信号，主窗口连接
  `_do_lock()`（内置已锁屏守卫）；系统解锁后再次锁定会再次触发。
- 意义：离开电脑按下 Win+L 后 TJKEY 立即锁屏，不再等应用自身的
  无操作超时。非 Windows 平台探测恒为 False，联动自然禁用。

### 26.3 滚动备份

- `vault_io.backup_file(path)`：保存替换前把上一版复制为 `<file>.bak`
  （手动读写 + fsync 落盘，保证 `.bak` 恒为文件且内容完整）。
  备份失败（磁盘满/权限/.bak 被目录占用）静默忽略，不阻塞正常保存。
- 覆盖范围：`save_vault`（每个 vault 文件）与 `accounts.save_accounts`
  （accounts.conf——存有全部账号哈希，损坏即所有账号失联）。
- 意义：误删条目后清空回收站、误改密、或写入逻辑缺陷产生错误内容时，
  始终有一份"上一版"可回退；改密重加密前也会留下旧密钥版本的备份。
- 注意：`.bak` 文件以明文 JSON 存在于 vaults/ 目录（与 vault 本体相同的
  敏感级别），随云盘同步，请勿手动编辑；`detect_conflict_files` 不会把
  `.bak` 误判为冲突副本。

### 26.4 Windows 剪贴板历史说明（README）

- 30 秒自动清空只能清除"当前"剪贴板；Windows 10/11 的剪贴板历史
  （Win+V）会在系统中保留复制过的密码，属于平台限制。
- README 安全设计章节已补充说明与处置建议：系统设置 → 系统 → 剪贴板
  → 关闭"剪贴板历史记录"，或在历史中手动删除敏感条目。

## 27. 单机升级与双机并存操作指引

面向用户的操作手册：单机升级顺序、双机新旧程序并存（混合
version）拉扯的处置顺序、误用旧程序保存后的恢复路径与时间点。
机制细节见 18.6（菜单 [7]）、23.1（登录自动升版）、26.3（滚动
备份）；README《单机升级与双机并存》一节提供同内容的一页速查版。

### 27.1 单机升级流程

1. **冷备份**：复制 `MyVault/vaults/`（各 `.vault` 与
   `accounts.conf`）到 MyVault 之外。`.bak` 仅保留最近一版、与原
   文件同目录且同样被云同步覆盖（见 26.3），不能替代冷备份。
2. 升级程序本体（数据在 MyVault，不随程序目录移动）。
3. 启动新版并登录：version 1 自动迁移 version 2（两遍式 + 外部
   修改哈希保护，失败不写盘、不阻断登录，见 23.1）。
4. 核对条目后完成；不再回退则删除旧版程序目录防误开。

### 27.2 双机并存处置顺序（混合 version 拉扯）

原则：**所有机器先升级程序，再打开数据文件**。已出现拉扯时：

1. 两台机器完全退出 TJKEY（旧版持有过期内存快照，继续保存会
   与云同步互相拉扯）。
2. 等云盘同步完成（两边文件大小/修改时间一致）。
3. 旧版报"不支持的 Vault 文件版本"＝文件已是 version 2：文件
   没坏，在旧版机器安装新版后登录即可，文件无需改动。
4. 确需回退某台到旧版：先在新版用菜单 [7]（见 18.6）降级为
   version 1，再换旧版打开；新版再登录会自动升回 version 2。
5. 各机版本一致前，不在任何一台上保存。

### 27.3 误用旧程序保存后的恢复与时间点

先全部退出、等云盘同步完成，再按可得性选恢复源：

| 恢复源 | 恢复到的时间点 | 操作 |
|---|---|---|
| `vaults/<账号>.vault.bak` | 最近一次保存之前（仅一版，可能已被更晚保存滚动掉） | 复制改名为原文件名覆盖回 `vaults/` |
| 升级前冷备份 | 手动复制的那一刻 | 覆盖回 `MyVault/vaults/`（必要时连同 `accounts.conf`） |
| 均无 | — | 只能接受当前文件；`recover.py` 只能解密现有数据，无法还原历史版本 |

覆盖恢复后：v1 文件由新版登录自动升版（或菜单 [7] 手动升）；
v2 冷备份要给旧版用则先菜单 [7] 降级。核对无误后立即保存一次，
使云盘以恢复后的文件为准（恢复期间各机保持退出）。

### 27.4 用户速查（出问题照抄）

- 旧版报"不支持的 Vault 文件版本"：文件没坏——全部机器升级后再
  打开；要回退才用菜单 [7] 降级，且先降级、后换旧版。
- 疑似被写坏/写回旧内容：全部退出 → 等同步 → `.bak` 或冷备份
  覆盖 → 新版登录核对 → 立即保存。
- 要回退旧版程序：新版菜单 [7] 降级 → 再换旧版；严禁先开旧版。
- 拿不准：先复制 `MyVault/vaults/` 到别处再操作。

---

## 附录A：字段类型速查表

| type | 存储 | 界面显示 | 复制行为 | 到期检测 | 搜索 |
|---|---|---|---|---|---|
| `text` | 明文 | 直接显示 | 复制值 | 否 | 搜索 label+value |
| `secret` | ENC:加密 | ●●●●●●●● | 解密后复制 | 否 | 只搜索 label |
| `date` | 明文 YYYY-MM-DD | 直接显示 | 复制日期 | 是 | 搜索 label |
| `date_domain` | 明文 域名\|日期 | 两列显示 | 复制域名 | 是（日期部分） | 搜索域名部分+label |

---

## 附录B：ID 生成规则

| ID 类型 | 前缀 | 随机部分 | 示例 |
|---|---|---|---|
| 大类 | `cat_` | 6位字母数字 | `cat_a1b2c3` |
| 小类 | `sub_` | 6位字母数字 | `sub_d4e5f6` |
| 条目 | `entry_` | 6位字母数字 | `entry_g7h8i9` |
| 字段 | `fld_` | 3位数字 | `fld_001` |
| 模板（内置） | `tpl_builtin_` | 3位数字 | `tpl_builtin_001` |
| 模板（自定义） | `tpl_custom_` | 6位字母数字 | `tpl_custom_a1b2c3` |

字段 ID 在条目内唯一即可，其他 ID 全局唯一。

---

## 附录C：错误处理规范

| 场景 | 处理方式 |
|---|---|
| app.config 不存在 | 触发首次启动引导 |
| vault 文件损坏/JSON解析失败 | 弹窗提示，建议检查云盘同步，不允许进入主界面 |
| 解密失败（密码错误）| 登录界面提示"密码错误" |
| 解密失败（数据损坏）| 详情面板该字段显示"[解密失败]"，不崩溃 |
| 登录密码正确但 vault 无法解密（配置与数据错位）| 拦截登录、清空会话，提示检查 vaults/ 目录（见 23.1） |
| vault 文件被外部修改后保存 | 拒绝写入，弹窗说明并强制锁屏回登录界面（见 23.2） |
| vault 文件写入失败（磁盘满等）| 弹窗提示，内存状态保留，允许重试 |
| 保存的日期字段格式非法 | 保存时拦截并提示修正（不会静默写入） |
| 打开非 http/https 网址 | 弹窗拦截，提示手动复制到浏览器（见 23.4） |
| kdf_params.iterations 非法/缺失 salt | 派生函数抛 ValueError，登录与 recover.py 均明确报错，不假死 |
| 检测到冲突文件 | 弹窗提示，不阻塞使用 |
| 导出文件路径无写权限 | 弹窗提示，让用户重新选择路径 |

---

*文档版本：v1.1（2026-09-08 增补第 23/24 章及安全加固说明）| 项目名称：TJKEY | 语言：Python + PySide6*
