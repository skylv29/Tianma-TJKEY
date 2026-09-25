# tests/test_suites.py
# pytest 集成层：以子进程方式运行全部模块自测与分轮验证脚本。
#
# 各脚本（crypto.py / vault_io.py / ... / _test_p5_reliability.py）内部
# 会创建独立的临时环境与 QApplication，必须进程级隔离才能互不污染，
# 因此这里不做 import，而是逐个 subprocess 运行并断言退出码为 0。
# CI（.github/workflows/tests.yml）与本机 `python -m pytest tests`
# 都经由本文件执行全部验证。

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据层模块自测 + 各轮修复/功能验证脚本 + 全流程端到端测试
SCRIPTS = [
    "crypto.py",
    "vault_io.py",
    "accounts.py",
    "_test_aad_consistency.py",
    "_test_migration_integrity.py",
    "_test_login_upgrade_confirm.py",
    "_test_p1_fixes.py",
    "_test_p2_fixes.py",
    "_test_p3_fixes.py",
    "_test_p3_round2.py",
    "_test_p4_features.py",
    "_test_p5_reliability.py",
    "_test_e2e_full.py",
    # 打包冒烟：PyInstaller 全量打包 + dist 产物 --smoke + 数据文件混入扫描。
    # 耗时约 1-3 分钟且依赖 pyinstaller；CI 未装 pyinstaller 时脚本退出码 79，
    # 本文件转为 pytest.skip()（与“通过”可区分）；本地可用
    # TJKEY_SKIP_PACKAGING_SMOKE=1 跳过（同样 exit 79）。
    # 放在最后：前 12 项快速失败，不必等打包才暴露问题。
    "_test_packaging_smoke.py",
]


SKIP_EXIT_CODES = {
    79: "打包冒烟脚本主动跳过（未装 pyinstaller 或 TJKEY_SKIP_PACKAGING_SMOKE）",
}


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_passes(script):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # 打包冒烟内部预算 60+480+60=600，外层留出探测与输出捕获余量
    timeout = 720 if script == "_test_packaging_smoke.py" else 600
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, script)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode in SKIP_EXIT_CODES:
        pytest.skip(f"{script}: {SKIP_EXIT_CODES[result.returncode]}；"
                    f"stdout: {result.stdout.strip()[-500:]}")
    assert result.returncode == 0, (
        f"{script} 验证失败：\n...stdout 末尾 3000 字符...\n{result.stdout[-3000:]}\n"
        f"--- stderr 末尾 3000 字符 ---\n{result.stderr[-3000:]}")
