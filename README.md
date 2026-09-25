# TJKEY

本地密码管理器，基于 PySide6 构建，支持多账号、分类管理、加密存储、到期提醒和数据导出。

## 功能特性

- **多账号系统** — 独立 vault 文件，互不干扰
- **加密存储** — AES-256-GCM 加密敏感字段，PBKDF2 密钥派生（60 万轮）；
  version 2 格式将密文与条目/字段 ID 绑定（AAD），防止字段搬移攻击
- **分类管理** — 大类/小类两级分类，支持拖拽排序
- **条目管理** — 基于模板创建，支持自定义字段、拖拽排序
- **密码生成器** — 随机强密码一键生成，长度/字符类可配置，可排除易混淆字符
- **回收站** — 删除的条目进入回收站，可恢复或永久删除
- **应用内改密** — 设置中直接修改登录密码，自动重加密数据文件
- **首次引导建号** — 首次使用可直接在向导中创建第一个账号
- **到期提醒** — 自动扫描域名/日期字段，红/黄/绿三级提醒
- **全文搜索** — 搜索条目名称、分类、字段内容
- **数据导出** — Markdown 格式导出（需二级密码验证）
- **主题切换** — 深色/浅色主题
- **自动锁屏** — 可配置无操作超时时间
- **灾难恢复** — 独立 recover.py 工具手动解密 vault 文件
- **数据格式自动升级** — version 1 旧文件登录时自动迁移到 version 2；
  可用 vault_admin 菜单 [7] 手动升/降级

## 环境要求

- Python 3.11+
- PySide6
- cryptography

## 快速上手

### 方式一：从源码运行（需要 Python 3.11+）

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

首次运行会引导设置 MyVault 存储目录。

### 方式二：免安装（从 Releases 下载）

1. 在 GitHub Releases 页面下载最新版 `TJKEY-x.y.z.zip` 并解压。
2. 双击 `TJ-KEY\TJ-KEY.exe` 启动，无需安装 Python。
3. 首次启动若出现 Windows SmartScreen 蓝色提示"Windows 已保护你的电脑"，
   点击**更多信息 → 仍要运行**即可（程序未做代码签名属正常现象）。

## 项目结构

```
TJKEY/
├── main.py                 # 程序入口
├── session.py              # 全局会话状态
├── crypto.py               # 加密核心（AES-256-GCM, PBKDF2）
├── vault_io.py             # Vault 文件读写、CRUD 操作
├── accounts.py             # 账号管理
├── icons.py                # SVG 图标资源
├── markdown_export.py      # Markdown 导出共享模块（导出对话框/恢复工具共用）
├── ui/
│   ├── main_window.py      # 主窗口（三栏布局）
│   ├── login.py            # 登录窗口
│   ├── nav_panel.py        # 左侧导航面板
│   ├── entry_list.py       # 中间条目列表面板（含拖拽排序）
│   ├── entry_detail.py     # 右侧详情面板
│   ├── entry_edit.py       # 编辑面板（含密码生成器）
│   ├── vault_sync.py       # 统一保存入口（外部修改检测、强制锁屏）
│   ├── change_password_dialog.py  # 修改登录密码对话框
│   ├── export_dialog.py    # 导出对话框
│   ├── settings_dialog.py  # 设置对话框
│   └── template_manager.py # 模板管理器
├── styles/
│   ├── __init__.py         # 主题管理
│   ├── dark.py             # 深色主题
│   └── light.py            # 浅色主题
├── vault_admin.py          # 独立账号管理工具
├── recover.py              # 灾难恢复工具
└── assets/                 # 图标资源
```

## 数据存储

所有数据存储在用户指定的 MyVault 目录下：

```
MyVault/
├── app.conf                # 用户偏好（主题、锁屏时间）
├── accounts.conf           # 账号列表和密码哈希
└── vaults/
    └── <username>.vault    # 各账号的加密数据文件（JSON 格式）
```

### Vault 文件结构

```json
{
  "version": 2,
  "account": "用户名",
  "kdf_params": { "algorithm": "pbkdf2", "hash": "sha256", "iterations": 600000, "salt": "..." },
  "categories": [{ "id": "cat_xxx", "name": "大类名", "order": 0, "subcategories": [...] }],
  "templates": [{ "id": "tpl_xxx", "name": "模板名", "fields": [...] }],
  "entries": [{ "id": "entry_xxx", "name": "条目名", "category_id": "cat_xxx", "order": 0, "fields": [...] }]
}
```

**`version` 字段说明：**

| 值 | 含义 |
|----|------|
| `1` | 旧格式：密文不绑定位置，可被搬到其他字段仍能解密 |
| `2` | 当前格式：密文附带 `entry_id + field_id` 认证（AAD），位置不符即拒绝解密 |

- 新建账号直接生成 version 2 文件
- version 1 旧文件在**下次登录时自动升级**为 version 2（验证密钥可用后
  原地迁移，失败则本次仍按 v1 使用、下次登录重试，不阻断登录）
- 回退旧版程序前，先用 `vault_admin.py` 菜单 [7] 把文件降级回 version 1

> **云同步警告**：version 2 文件无法被旧版程序打开（会明确报
> "不支持的 Vault 文件版本"）。多台电脑通过云盘共享同一 MyVault 时，
> **必须所有机器先升级程序，再打开数据文件**。旧版程序若已打开过该文件，
> 请先用菜单 [7] 降级，或确认所有电脑都已升级后再继续使用。

### 字段类型

| 类型 | 说明 | 加密 |
|------|------|------|
| `text` | 普通文本 | 否 |
| `secret` | 密码/密钥 | AES-256-GCM |
| `date` | 日期 | 否 |
| `date_domain` | 域名+到期日期 | 否 |

## 安全设计

- 密钥只在内存中，程序关闭后消失
- 每个 vault 文件有独立的 salt
- 加密字段格式 `ENC:base64(IV+密文+认证标签)`，可用 recover.py 独立解密
- **AAD 字段位置绑定（version 2）**：密文与 `entry_id + field_id` 一起
  参与 AES-GCM 认证——把密文复制/搬到其他条目或字段会解密失败，
  防止攻击者重排密文位置
- 密码使用 PBKDF2-SHA256 哈希存储
- 保存时先写临时文件再原子替换，防止写入中断损坏数据
- 保存前校验 vault 文件内容未被外部程序修改（云盘同步 / vault_admin），
  防止内存中的旧快照覆盖外部修改导致数据无法解密
- 格式迁移（登录自动升版 / 菜单 [7] 升降级）采用两遍式转换 +
  外部修改哈希保护，任一字段失败则整体不写盘，不产生半迁移文件
- 单实例锁：已有 TJKEY 在运行时拒绝第二个实例启动，避免双开保存冲突
- 系统锁屏联动：Windows 会话锁定（Win+L）时立即锁屏，无需等应用超时
- 滚动备份：vault 文件与 accounts.conf 每次保存前将上一版复制为 `.bak`
- 复制的密码 30 秒后自动清空剪贴板（仅当内容未被用户替换时）

> **云同步升级顺序（重要）**：version 2 数据文件旧版程序无法打开。
> 多台电脑共享同一云盘 MyVault 时，**必须所有机器先升级程序，再打开
> 数据文件**；回退旧版程序前先用 vault_admin 菜单 [7] 降级文件格式。

**关于 Windows 剪贴板历史（Win+V）**：Windows 10/11 的剪贴板历史会
保留复制过的内容，30 秒自动清空只能清除"当前"剪贴板，无法触及历史
记录。如果系统开启了剪贴板历史，建议：设置 → 系统 → 剪贴板 → 关闭
"剪贴板历史记录"；或在历史中手动删除敏感条目。

## 管理工具

```bash
# 账号管理（创建/删除/修改密码/升降级数据格式）
# 菜单 [7]「升级/降级数据文件格式」：version 1 ⇄ 2 手动双向转换，
# 回退旧版程序前用它把文件降回 version 1
python vault_admin.py

# 灾难恢复（手动解密 vault 文件中的加密字段，兼容 version 1/2）
python recover.py
```

## 单机升级与双机并存（混合 version 处置指引）

version 1 / version 2 文件并存时，旧版程序打不开 v2 文件（报
"不支持的 Vault 文件版本"）。以下按场景给出操作顺序，出问题
可直接照抄最后一节。

### 单机升级流程（推荐顺序）

1. **先做冷备份**：把 `MyVault/vaults/` 整个目录（各 `.vault`
   与 `accounts.conf`）复制到 MyVault **之外**（U 盘/桌面文件夹）。
   `.bak` 只保留最近一版、与原文件同目录且会被后续写入和云同步
   覆盖，不能当升级保险。
2. 升级程序（新旧程序目录可并存，数据都在 MyVault，不随程序移动）。
3. 启动**新版**并登录：version 1 文件自动迁移为 version 2
   （两遍式转换，任一字段失败不写盘、不阻断登录，下次登录重试）。
4. 核对条目无误后升级完成；确认不再回退就删掉旧版程序目录，避免误开。

### 双机并存（一台新版、一台旧版共享云盘）处置顺序

**原则：所有机器先升级程序，再打开数据文件。** 已经出现拉扯时：

1. 两台机器**完全退出** TJKEY（旧版还开着会持有过期内存快照）。
2. 等云盘把 MyVault 同步完成（两边文件大小/修改时间一致）。
3. 旧版报"不支持的 Vault 文件版本"＝文件已是 version 2：文件没坏，
   在旧版机器上装新版，登录即可继续，文件不用动。
4. 确需回退某台机器到旧版程序：先在新版用 `vault_admin.py` 菜单
   [7] 把文件降回 version 1，**再**换旧版打开；新版再登录会自动
   升回 version 2。
5. 所有机器版本一致之前，**不要在任何一台上保存**。

### 误用旧程序保存后怎么恢复（回到哪个时间点）

先两台都退出程序、等云盘同步完成，再按可得性选恢复源（从近到远）：

| 恢复源 | 恢复到的时间点 | 操作 |
|--------|----------------|------|
| `vaults/<账号>.vault.bak` | **最近一次保存之前**（仅一版，可能已被更晚的保存滚动掉） | 把 `.bak` 复制改名为原 `.vault` 文件名，覆盖回 `vaults/` |
| 升级前冷备份 | **你手动复制的那一刻** | 把冷备份的 `.vault`（必要时连同 `accounts.conf`）复制回 `MyVault/vaults/` |
| 都没有 | — | 只能接受当前文件；`recover.py` 只能解密现有数据，救不出更早的历史 |

覆盖恢复之后：

- 恢复的是 version 1 文件（旧程序保存的）→ 新版登录时自动升 v2；
  恢复的是 version 2 冷备份但要给旧版用 → 新版 `vault_admin.py`
  菜单 [7] 降级后再换旧版打开。
- 登录核对条目无误后**立即保存一次**，让云盘以你刚恢复的文件
  为准（恢复期间两台都要保持退出）。

### 出问题照抄（一页速查）

1. **旧版报"不支持的 Vault 文件版本"** → 文件没坏：所有机器装
   新版，全部升级后再打开；要回退才用菜单 [7] 降级，且先降级、
   后换旧版。
2. **怀疑被旧程序写坏/写回旧内容** → 全部退出 → 等云盘同步 →
   用 `vaults/<账号>.vault.bak` 或升级前冷备份覆盖回去 → 新版
   登录核对 → 立即保存一次。
3. **要回退旧版程序** → 新版 `vault_admin.py` 菜单 [7] 降级 →
   再换旧版打开；严禁先开旧版再想补救。
4. **拿不准就先备份** → 复制 `MyVault/vaults/` 到别处，再动任何
   操作。

## 开发与测试

项目采用"模块自测 + 分轮修复验证脚本"两层验证，均为标准 Python 脚本，无需额外测试框架：

```bash
# 数据层模块自测（无窗口依赖）
python crypto.py        # 加密/解密/密码哈希/畸形输入防护/AAD 构造
python vault_io.py      # vault 读写/CRUD/重加密/冲突文件检测/格式迁移
python accounts.py      # 账户/改密/断电自愈/路径穿越防护

# 分轮修复验证脚本（离屏运行，无需显示窗口）
python _test_aad_consistency.py  # AAD 双实现（crypto/recover）逐字节一致
python _test_p1_fixes.py     # 登录密钥校验、锁屏面板清理、编辑面板防二次加密
python _test_p2_fixes.py     # vault 外部修改检测、迭代次数以文件为准、URL 协议白名单
python _test_p3_fixes.py     # 导出统一、剪贴板自动清空、首次引导流程
python _test_p3_round2.py    # 配置深拷贝、导出加固、日期校验等优化项
python _test_p4_features.py  # 密码生成器/应用内改密/引导建号/回收站
```

每个脚本全部断言通过时会输出 `=== ... 验证通过 ===`。修改 `crypto.py` / `vault_io.py` / `accounts.py` 任一核心模块后，建议跑完全部脚本再交付。各机制的设计说明见《TJKEY_项目文档.md》第 23 章。

### pytest 与 CI

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests        # 以子进程运行上面全部脚本（约 20 秒）
```

`tests/test_suites.py` 是 pytest 集成层：各脚本内部会创建独立环境与
QApplication，必须进程级隔离，因此以子进程逐个运行并断言退出码。
推送到 GitHub 后 `.github/workflows/tests.yml` 会在 Windows/Linux
双平台自动运行全部验证。版本号统一维护在 `version.py`，变更记录见
`CHANGELOG.md`。

## 从源码打包

```bash
pip install -r requirements-dev.txt
pyinstaller build.spec --noconfirm
```

- 产物：`dist/TJ-KEY/TJ-KEY.exe`（+ `_internal/` 依赖目录），无需安装 Python 即可运行。
- `vault_admin.py`、`recover.py`、`markdown_export.py` 打包时自动复制到 exe 同目录（账户管理与灾难恢复工具，按需使用）。
- 打包配置见 `build.spec`（已适配 PyInstaller 6.x）；`build/` 为中间产物，可删除。详细说明见《TJKEY_项目文档.md》第 20 章。

## 免责声明

- 本程序所有数据**仅存储在本机**（你指定的 MyVault 目录），不上传任何服务器，
  也不提供云同步功能（使用第三方云盘同步 MyVault 属于你的自行选择）。
- 主密码由你本人设定、仅在内存中使用，**丢失后无法恢复**——作者没有任何
  后门，也无法帮你找回数据。
- 请在升级、回退或批量修改数据文件前先做冷备份（用 `vault_admin.py` 或手动
  复制 `MyVault/vaults/` 目录）。
- 本软件按"现状"提供，作者不对任何数据丢失、泄露或损坏承担责任。

## 许可证

本项目采用 [MIT 许可证](LICENSE)，详见 [LICENSE](LICENSE) 文件。
