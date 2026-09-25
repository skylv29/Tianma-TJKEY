# build.spec
# TJKEY PyInstaller 打包配置（适配 PyInstaller 6.x）
#
# 使用方式（在 VaultApp 目录下执行）：
#   pip install "pyinstaller>=6.0"
#   pyinstaller build.spec --noconfirm
#
# 输出目录：dist/TJ-KEY/
# 可执行文件：dist/TJ-KEY/TJ-KEY.exe
#
# 三个工具脚本（vault_admin.py / recover.py / markdown_export.py）在
# 打包结束时自动复制到 exe 同目录，无需手动操作。其中 vault_admin /
# recover 在目标机需装有 Python 3.11+ 和 cryptography 才能运行。

import os

# 项目根目录
ROOT = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # 将 assets 文件夹打包进去（图标等）
        (os.path.join(ROOT, 'assets'), 'assets'),
    ],
    hiddenimports=[
        # PySide6 相关
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        # cryptography 相关
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings._rust',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型包，减小体积
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'test',
        'unittest',
    ],
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,         # onedir 模式：dll 单独放
    name='TJ-KEY',                 # 输出文件名 TJ-KEY.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # 不用 UPX 压缩（避免误报病毒）
    console=False,                 # 不显示命令行黑窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows 图标（运行 generate_icon.py 生成，或替换为自定义图标）
    icon=os.path.join(ROOT, 'assets', 'icon.ico')
        if os.path.isfile(os.path.join(ROOT, 'assets', 'icon.ico'))
        else None,
    # 注：icon.png 由 QApplication.setWindowIcon 在运行时加载，无需 spec 配置
    version=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TJ-KEY',                 # 输出文件夹名
)

# ── 附带工具脚本：打包结束自动复制到 exe 同目录（免手动操作）
import shutil
for _script in ('vault_admin.py', 'recover.py', 'markdown_export.py'):
    shutil.copy2(
        os.path.join(ROOT, _script),
        os.path.join(DISTPATH, coll.name, _script),
    )
