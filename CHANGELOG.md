# 更新日志（CHANGELOG）

TJKEY 的版本变更记录。各机制的详细说明见《TJKEY_项目文档.md》
第 23 章（安全加固）、第 25 章（功能补全）、第 26 章（可靠性增强）。

## [1.2.0] — 2026-09-23

### 数据格式升级（version 1 → 2，AAD 字段绑定）

- **vault 文件 version 2**：AES-256-GCM 加密时把
  `entry_id + field_id` 作为附加认证数据（AAD，前缀 `tjkey-v2|`）
  一并参与认证——把条目 A 的密文粘到条目 B 的位置会被认证标签
  拒绝，防止字段搬移攻击
- **登录升版先确认**：用 version 1 旧文件登录时，验证密钥可用后
  先弹确认框（默认按钮=升级；取消=放弃本次登录，数据文件零字节
  改动）；确认后才原地迁移到 version 2（两遍式解密/重加密 +
  外部修改哈希保护，任一失败不产生半迁移文件；失败则本次仍按
  v1 使用并提示 + 写崩溃日志，下次登录重试）
- **登录升版确认期间的外部修改防护**：确认后、迁移前重算磁盘
  SHA 与登录基准比对，不一致则锁屏取消登录、绝不进入迁移；迁移
  失败且重读到新数据时用当前密钥复验首个 ENC 字段，复验失败同样
  取消登录；`save_app_conf`/`update_app_conf` 对空 `myVault_path`
  抛 `ValueError`，防止把 `app.conf` 写到进程 cwd
- **升级即重写数据文件（冷备份提示）**：确认升级后会重写 vault
  数据文件（写前自动滚动备份上一版 `.bak`，仅保留最近一版）；
  `.bak` 与原文件同目录、同样会被云同步覆盖，**升级前建议在
  MyVault/vaults/ 之外另存一份冷备份**
- **vault_admin 新增菜单 [7]「升级/降级数据文件格式」**：
  手动双向转换，供回退旧版程序时把 v2 降回 v1
- **双实现防漂移测试**：`_test_aad_consistency.py` 断言
  `crypto.py` 与 `recover.py`（独立分发、不依赖 crypto.py）
  两份 AAD 实现对同一 (version, entry_id, field_id) 产出
  逐字节相同，覆盖空 ID / 中文 / Unicode / 缺 ID；
  已加入 `tests/test_suites.py` 清单
- **真实数据试运行工具**：`tools_trial_migration.py` 对
  myaccount.vault 只读复制到临时目录，完成 v1→v2→v1 双向试运行
  并输出三状态统计摘要（仅统计量，不打印明文/密文）
- **登录升版确认回归**：`_test_login_upgrade_confirm.py`
  覆盖"取消→文件 SHA 不变且 version 仍 1、不发射 login_success"
  与"确认→升为 v2 且字段可 AAD 解密"两条；已入 `tests/test_suites.py`

### 打包冒烟与审查修复

- **打包冒烟测试**：`_test_packaging_smoke.py` 全量 PyInstaller
  打包 + dist 产物 `--smoke`（LoginWindow + MainWindow 离屏构造，
  断言 stdout 含 `TJKEY smoke test OK`）+ 数据文件混入扫描；
  未装 pyinstaller 或 `TJKEY_SKIP_PACKAGING_SMOKE=1` 时退出码 79，
  `tests/test_suites.py` 转为 `pytest.skip()`（与"通过"可区分）；
  配套 `build/_run_packaging_smoke.bat` 先删旧 `smoke.exit` 再写入，
  轮询方 strip 尾随空格
- **PyInstaller 探测加固**：`_pyinstaller_available` 仅在
  ModuleNotFoundError/"No module named" 时判定为未安装（exit 79），
  其余异常按真实失败 exit 1，不再把损坏环境吞成跳过
- **疑似数据文件扫描扩展**：SUSPECT_RE 增加 `\.tmp$`、`~$`、
  冲突副本等宽松匹配，覆盖 `.bak`/`.tmp`/Office 临时文件
- **打包外层超时**：test_suites 打包项 timeout 提至 720s，
  与内部 60+480+60 预算留出余量
- **MainWindow 空路径守卫**：`_save_window_geometry` 在
  `session.myVault_path` 为空时不再把 `app.conf` 写到 cwd
- **venv**：根目录补建 `venv\`（pytest 9.1.1 + PyInstaller 6.22.3
  已装入），`.gitignore` 忽略 `venv/`；未改任何源码解释器路径

> [!WARNING]
> **云同步场景**：version 2 文件旧版程序无法打开（显式报
> "不支持的 Vault 文件版本"）。多台电脑通过云盘共享同一
> MyVault 时，**必须所有机器先升级程序，再打开数据文件**；
> 需要回退旧版程序时，先用 vault_admin 菜单 [7] 降级。

### 文档同步

- README / 项目文档：version 2 格式说明、登录自动升版行为、
  vault_admin 菜单 [7] 回退路径、云同步升级顺序警告
- recover.py：version > 2 明确拒绝退出；解密失败文案区分
  "字段位置不匹配"场景

## [1.1.0] — 2026-09-08

### 新功能（P4 功能补全）

- **密码生成器**：`crypto.generate_password`（CSPRNG、字符类可配、
  可排除易混淆字符），编辑面板密码字段一键生成
- **应用内修改登录密码**：设置入口，改密自动重加密数据文件并强制
  重新登录；错误分支不改动任何数据
- **首次引导建号**：向导内直接创建第一个账号，不再要求命令行
- **回收站**：删除改为软删除，可恢复/永久删除；列表、搜索、到期
  提醒、状态栏计数、登录校验全口径排除；程序内导出不包含、
  recover.py 全量导出包含

### 可靠性增强（P5）

- **单实例锁**：QLockFile 拒绝双开
- **系统锁屏联动**：Windows 会话锁定（Win+L）立即锁屏
- **滚动备份**：vault 文件与 accounts.conf 每次保存前保留上一版 `.bak`
- **剪贴板历史说明**：README 补充 Win+V 平台限制与处置建议

### 安全修复与加固（P1/P2/P3）

- **P1**：锁屏计时器在登录界面重复触发（叠加登录窗口）；
  剪贴板清空定时器随字段行销毁失效
- **P2**：vault 外部修改检测（内容哈希比对，防旧密钥快照覆盖
  新密钥文件）；KDF 迭代次数以 vault 文件记录为准；URL 打开仅
  放行 http/https
- **P3**：配置深拷贝、分类排序不丢数据、Markdown 导出加固
  （代码块围栏自适应/表格转义/孤儿条目归未分类）、编辑面板明文
  即时清理、日期格式校验、显示名称内存缓存、recover.py 畸形参数
  防护、死代码与未用 imports 清理
- **首批修复（09-07）**：登录密钥-数据匹配校验、锁屏面板明文清理、
  防 ENC: 二次加密、GUI 与 recover.py 导出统一、剪贴板自动清空等

### 界面与流程修复（用户实测反馈，2026-09-12）

- **修复搜索功能失效**：条目列表刷新逻辑缩进错位，搜索结果被当前分类
  视图覆盖；在具体分类下搜索直接抛 UnboundLocalError（由全流程 E2E
  测试抓出）
- 修复设置对话框内容裁剪：新增改密入口后固定高度溢出，设置/向导/
  建号/改密等对话框统一改为固定宽度、高度自适应
- 修复模板管理显示问题：新建模板按钮被裁剪（全局 QSS 把按钮撑到
  46px 压过 setFixedHeight）、切换模板时控件重叠闪现、字段行文字被
  裁剪、类型下拉只显示一项（无选择器的内联样式级联压扁了弹出列表）
- 控制台告警清理：锁屏信号改为启动时一次性连接；过滤无害的样式表
  解析告警

### 工程化补充

- 验证体系：3 个模块自测 + 7 个分轮/功能验证脚本 + 1 个全流程 E2E
  （`_test_e2e_full.py`，10 阶段用户旅程）
- pytest 集成：`tests/test_suites.py` 子进程运行全部脚本（10 项）
- GitHub Actions CI：Windows/Linux 矩阵
- 打包：`build.spec` 适配 PyInstaller 6.x，产出 `dist/TJ-KEY/TJ-KEY.exe`（三个工具脚本自动随包分发）
- 版本号统一为 `version.py` 单一来源；requirements 版本上限；
  .gitignore（app.config 等本机文件）

## [1.0.0] — 2026-04

- 首个完整版本：多账号、字段级加密（AES-256-GCM + PBKDF2 60 万轮）、
  大类/小类分类、模板系统、到期提醒、全文搜索、Markdown 导出
  （二级密码）、云盘冲突检测、深色/浅色主题、自动锁屏、
  vault_admin.py 账户管理、recover.py 灾难恢复
