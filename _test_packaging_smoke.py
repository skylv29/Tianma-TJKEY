# _test_packaging_smoke.py
# 打包冒烟测试：真实调用 PyInstaller 按 build.spec 打包 → 运行 dist 产物
# `TJ-KEY --smoke` 断言退出码 0 → 扫描产物目录，断言未混入
# .vault / accounts.conf / app.config 等数据文件。
#
# 跳过策略（取舍）：
#   1. TJKEY_SKIP_PACKAGING_SMOKE=1 → 打印原因、exit 79
#      （本机想跳过打包快速跑完整套件时用）；
#   2. 确认未安装 pyinstaller → 打印原因、exit 79
#      （CI（.github/workflows/tests.yml）只装 requirements.txt + pytest，
#      requirements.txt 不含 pyinstaller，因此 CI 本机这条会自动跳过，
#      不打破现有流水线；本地 requirements-dev.txt 含 pyinstaller>=6.0
#      则真实执行；探测失败（超时/异常退出）按真实失败 exit 1，不吞成跳过）；
#      exit 79 由 tests/test_suites.py 转为 pytest.skip()，与“通过”可区分；
#   3. 正常执行约 1-3 分钟（onedir 全量重打包），tests/test_suites.py
#      timeout=720 秒内足够完成。
# 打包产物 dist/ 与日志 build/packaging_smoke.log 均保留不删除
# （dist 是交付物，日志在 .gitignore 的 build/ 内）。

import os
import re
import subprocess
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(ROOT, "build", "packaging_smoke.log")
SKIP_ENV = "TJKEY_SKIP_PACKAGING_SMOKE"

# 出现在 dist 内即视为打包混入了用户数据，必须失败。
# 覆盖主文件名（大小写不敏感）、原子写残留 *.tmp、编辑器备份 *~、
# 云同步冲突副本宽松形态（accounts*.conf / sky*.vault）、.bak 与 .vault。
SUSPECT_RE = re.compile(
    r"(^|[/\\])(accounts[\w\-.() ]*\.conf|app\.config|app\.conf|tjkey\.lock)$"
    r"|sky[\w\-.() ]*\.vault$"
    r"|\.vault$"
    r"|\.bak$"
    r"|\.tmp$"
    r"|~$",
    re.IGNORECASE,
)

# test_suites.py 识别此退出码后调用 pytest.skip()，使“跳过”与“通过”可区分
SKIP_EXIT_CODE = 79


def _exe_path() -> str:
    """按平台给出打包产物可执行文件路径（Windows 为 .exe）。"""
    if os.name == "nt":
        return os.path.join(ROOT, "dist", "TJ-KEY", "TJ-KEY.exe")
    return os.path.join(ROOT, "dist", "TJ-KEY", "TJ-KEY")


def _pyinstaller_available() -> bool | None:
    """探测 pyinstaller。

    返回 True  → 可用；
    返回 None  → 确认未安装（ModuleNotFoundError / "No module named"），应跳过；
    其余异常或异常退出码 → 按真实失败处理（调用方 exit 1），不得吞成跳过。
    """
    try:
        r = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        print(f"[打包冒烟] 失败：探测 pyinstaller 异常：{type(e).__name__}: {e}",
              flush=True)
        return "error"
    err = (r.stderr or "") + (r.stdout or "")
    if r.returncode == 0:
        return True
    if "ModuleNotFoundError" in err or "No module named" in err:
        return None
    print(f"[打包冒烟] 失败：pyinstaller 探测退出码 {r.returncode}；"
          f"输出尾部：{err.strip()[-500:]}", flush=True)
    return "error"


def _tail(path: str, lines: int = 40) -> str:
    """读取日志文件末尾若干行用于失败/成功报告。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception as e:
        return f"<读取 {path} 失败: {e}>"


def _scan_suspects(dist_dir: str) -> list:
    """递归扫描 dist，返回混入的数据文件可疑清单。"""
    bad = []
    for dirpath, dirnames, filenames in os.walk(dist_dir):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, dist_dir)
            if SUSPECT_RE.search(rel.replace(os.sep, "/")):
                bad.append(rel)
        for d in dirnames:
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, dist_dir)
            if SUSPECT_RE.search(rel.replace(os.sep, "/")):
                bad.append(rel + "/")
    return bad


def _run() -> int:
    # ── 跳过条件 1：环境变量强制跳过（专用退出码，与“通过”区分）
    if os.environ.get(SKIP_ENV, "").strip().lower() not in ("", "0", "false"):
        print(f"[打包冒烟] 已按 {SKIP_ENV} 跳过", flush=True)
        return SKIP_EXIT_CODE

    # ── 跳过条件 2：确认未安装 pyinstaller（CI 场景）；探测失败≠未安装
    pyi = _pyinstaller_available()
    if pyi is None:
        print("[打包冒烟] 跳过：当前环境未安装 pyinstaller"
              "（CI 不装 pyinstaller；本地执行 "
              "pip install -r requirements-dev.txt 后可真实打包验证）",
              flush=True)
        return SKIP_EXIT_CODE
    if pyi is not True:
        return 1  # 探测异常已在 _pyinstaller_available 内打印原因

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

    # ── 1. 真实调用 PyInstaller 打包（日志写入 build/packaging_smoke.log）
    print("[打包冒烟] 开始 PyInstaller 打包（build.spec --noconfirm）...",
          flush=True)
    t0 = time.monotonic()
    with open(LOG_PATH, "w", encoding="utf-8") as logf:
        try:
            pack = subprocess.run(
                [sys.executable, "-m", "PyInstaller",
                 "build.spec", "--noconfirm"],
                cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT,
                timeout=480,
            )
        except subprocess.TimeoutExpired:
            print("[打包冒烟] 失败：打包超过 480 秒超时；日志尾部：",
                  flush=True)
            print(_tail(LOG_PATH), flush=True)
            return 1
    cost = time.monotonic() - t0
    if pack.returncode != 0:
        print(f"[打包冒烟] 失败：PyInstaller 退出码 {pack.returncode}，"
              f"耗时 {cost:.1f}s；日志尾部：", flush=True)
        print(_tail(LOG_PATH), flush=True)
        return 1
    print(f"[打包冒烟] 打包成功，耗时 {cost:.1f}s", flush=True)

    # ── 2. 运行 dist 产物 --smoke，断言退出码 0
    exe = _exe_path()
    if not os.path.isfile(exe):
        print(f"[打包冒烟] 失败：未找到产物 {exe}", flush=True)
        return 1
    env = os.environ.copy()
    # 强制使用平台默认 Qt 插件（windows）：offscreen/qminimal 插件未必
    # 被打进 onedir 产物，继承 offscreen 会造成假失败
    env.pop("QT_QPA_PLATFORM", None)
    try:
        smoke = subprocess.run(
            [exe, "--smoke"], cwd=os.path.dirname(exe),
            env=env, capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("[打包冒烟] 失败：运行产物 --smoke 超时（60 秒）", flush=True)
        return 1
    out = (smoke.stdout or "") + (smoke.stderr or "")
    print(f"[打包冒烟] 产物 --smoke 退出码 {smoke.returncode}；输出：",
          flush=True)
    print(out.strip()[-3000:], flush=True)
    if smoke.returncode != 0:
        print("[打包冒烟] 失败：dist 产物 --smoke 非 0 退出", flush=True)
        return 1
    # 退出码 0 还不够：必须看到成功哨兵，防止走了非冒烟路径的 0 退出
    if "TJKEY smoke test OK" not in out:
        print("[打包冒烟] 失败：产物 --smoke 退出码 0 但输出缺少成功哨兵 "
              "\"TJKEY smoke test OK\"", flush=True)
        return 1

    # ── 3. 扫描产物，断言没有混入数据文件
    dist_dir = os.path.join(ROOT, "dist")
    if not os.path.isdir(dist_dir):
        print("[打包冒烟] 失败：dist/ 目录不存在", flush=True)
        return 1
    suspects = _scan_suspects(dist_dir)
    if suspects:
        print("[打包冒烟] 失败：产物中发现疑似数据文件（打包混入用户数据）：",
              flush=True)
        for s in suspects:
            print(f"  - {s}", flush=True)
        return 1

    total = sum(len(f) for _, _, f in os.walk(dist_dir))
    print(f"[打包冒烟] 产物扫描通过：共 {total} 个文件，无数据文件混入",
          flush=True)
    print("=== 打包冒烟验证通过 ===", flush=True)
    return 0


if __name__ == "__main__":
    try:
        code = _run()
    except Exception:
        traceback.print_exc()
        code = 1
    print(f"[packaging-smoke] exit={code}", flush=True)
    sys.exit(code)
