# main.py
# TJKEY 程序总入口
#
# 启动流程：
#   0. 单实例锁（QLockFile，防止双开）
#   1. 创建 QApplication
#   2. 应用主题
#   3. 检查 app.config → 必要时显示首次引导
#   4. 显示登录界面
#   5. 登录成功后打开主窗口
#   6. 主窗口锁屏时回到登录界面（循环）

import os
import sys

# 确保能找到同目录下的所有模块
APP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP_DIR)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QLockFile, qInstallMessageHandler
from PySide6.QtGui import QIcon

from session import session
from accounts import load_app_conf, read_app_config
from version import APP_VERSION
from styles import apply_theme, DARK


def _install_qt_message_filter():
    """
    过滤 Qt 对"样式表解析失败"的控制台告警。

    背景：部分环境下 Qt 会对某些 QLabel 的样式表打
    "Could not parse stylesheet of object ..." 告警。该告警是无害杂讯：
    解析失败时 Qt 按尽力而为策略继续应用其余规则，界面显示不受影响，
    且无法在测试环境中稳定复现（离屏/真实平台、深浅主题均无）。
    只过滤这一条；其余 Qt 消息照常输出到 stderr。
    """
    import sys

    def _handler(msg_type, context, message):
        if "Could not parse stylesheet of object" in message:
            return
        sys.stderr.write(message + "\n")
        sys.stderr.flush()

    qInstallMessageHandler(_handler)


def main():
    _install_qt_message_filter()

    # ── 0. 单实例锁：防止双开导致保存冲突
    # 双开后第二个实例的保存会被外部修改检测拦截（强制回登录），
    # 虽不损坏数据，但体验混乱；这里直接拒绝第二个实例启动。
    lock = QLockFile(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "tjkey.lock"))
    if not lock.tryLock(0):
        app_stub = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.warning(
            None, "TJKEY 已在运行",
            "TJKEY 已有一个实例正在运行。\n"
            "请使用已打开的窗口，或先退出它再重新启动。")
        sys.exit(0)

    # ── 1. 创建 QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("TJKEY")
    app.setApplicationDisplayName("TJKEY")
    app.setOrganizationName("TJKEY")
    app.setApplicationVersion(APP_VERSION)



    # 设置应用图标
    # 优先使用 ICO（多尺寸，Windows 任务栏更清晰），回退到 PNG
    ico_path = os.path.join(APP_DIR, "assets", "icon.ico")
    png_path = os.path.join(APP_DIR, "assets", "icon.png")
    if os.path.isfile(ico_path):
        app.setWindowIcon(QIcon(ico_path))
    elif os.path.isfile(png_path):
        app.setWindowIcon(QIcon(png_path))

    # ── 2. 读取 MyVault 路径，确定初始主题
    myVault_path = read_app_config(APP_DIR)
    if myVault_path and os.path.isdir(myVault_path):
        try:
            conf = load_app_conf(myVault_path)
            theme = conf.get("theme", DARK)
        except Exception as e:
            sys.stderr.write(f"[TJKEY] 读取主题配置失败，回退深色主题：{e}\n")
            theme = DARK
    else:
        theme = DARK

    apply_theme(app, theme)

    # ── 3. 首次引导 / 获取 MyVault 路径
    from ui.login import check_and_setup, get_app_dir
    verified_path = check_and_setup(APP_DIR)

    if not verified_path:
        # 用户关闭了引导窗口，退出
        sys.exit(0)

    session.myVault_path = verified_path

    # 路径确定后重新读取主题（可能刚完成首次引导）
    try:
        conf = load_app_conf(verified_path)
        theme = conf.get("theme", DARK)
        apply_theme(app, theme)
    except Exception as e:
        sys.stderr.write(f"[TJKEY] 读取主题配置失败，保持当前主题：{e}\n")

    # ── 4. 主循环：登录 → 主窗口 → 锁屏 → 登录 → …
    from ui.login import LoginWindow
    from ui.main_window import MainWindow

    main_window = MainWindow()
    session.main_window = main_window

    def show_login():
        """显示登录界面，登录成功后打开主窗口。"""
        login_win = LoginWindow(verified_path)

        def on_login_success():
            login_win.hide()
            login_win.deleteLater()
            main_window.on_login()
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

        login_win.login_success.connect(on_login_success)
        login_win.show()
        login_win.raise_()
        login_win.activateWindow()

    # 锁屏信号只连接一次：处理函数仅引用稳定的 main_window/show_login，
    # 无需每次 show_login 时断开重连。旧实现每次都 disconnect+reconnect，
    # 而首次启动并无连接可断，libpyside 会先打一行 RuntimeWarning 再抛
    # 被捕获的 RuntimeError——日志噪音的来源。
    def _on_lock_requested():
        main_window.hide()
        show_login()

    main_window.lock_requested.connect(_on_lock_requested)

    show_login()

    sys.exit(app.exec())


def _write_crash_log(exc_text: str) -> str:
    """把未捕获异常追加写入本地崩溃日志，返回日志路径。"""
    log_dir = os.path.join(
        os.environ.get("LOCALAPPDATA") or APP_DIR, "TJKEY")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "crash.log")
    from datetime import datetime
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now().isoformat()} =====\n")
        f.write(exc_text)
    return log_path


def _smoke_test() -> int:
    """
    打包冒烟自检（--smoke）：初始化 QApplication → 构建登录窗口 +
    主窗口（均不 show、不进事件循环）→ 退出。不取单实例锁、不做首次
    引导、不读写任何数据文件；任一步失败返回非 0。正常启动路径不经过
    本函数，行为零改变。
    """
    import traceback
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setApplicationName("TJKEY")
        app.setApplicationDisplayName("TJKEY")
        app.setOrganizationName("TJKEY")
        app.setApplicationVersion(APP_VERSION)
        _install_qt_message_filter()
        apply_theme(app, DARK)
        # 空路径：_load_defaults 的读取失败均在其 try/except 内静默
        # 返回默认值，全程只读，不触碰真实 MyVault 数据
        from ui.login import LoginWindow
        win = LoginWindow("")
        win.close()
        win.deleteLater()
        # 主窗口同样在“未登录、无数据”下构造（build/_probe_mainwindow.py
        # 实验证实安全：_load_conf 空路径回退默认值，refresh 系列对
        # vault_data=None 直接返回），覆盖打包缺失主窗口链路资源的问题。
        # 不调用 close()：closeEvent 会走 _save_window_geometry 等退出
        # 清理路径，冒烟只验证“构造成功”，避免任何副作用
        from ui.main_window import MainWindow
        mwin = MainWindow()
        mwin.deleteLater()
    except Exception:
        # console=False 下 stdout/stderr 可能为 None 或断管，输出需兜底
        try:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
        except Exception:
            pass
        return 1
    try:
        if sys.stdout is not None:
            sys.stdout.write("TJKEY smoke test OK\n")
            sys.stdout.flush()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    import traceback
    if "--smoke" in sys.argv[1:]:
        # 打包冒烟自检分支：不进入正常启动流程（不取锁/不引导/不进事件循环）
        sys.exit(_smoke_test())
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # 打包后 console=False，未捕获异常若不处理会静默崩溃
        tb_text = traceback.format_exc()
        log_path = ""
        try:
            log_path = _write_crash_log(tb_text)
        except Exception:
            traceback.print_exc()
        try:
            app_stub = QApplication.instance() or QApplication(sys.argv)
            detail = f"详细信息已写入：\n{log_path}" if log_path else tb_text
            QMessageBox.critical(
                None, "TJKEY 运行错误",
                f"程序发生未处理的错误，即将退出。\n\n{detail}")
        except Exception:
            traceback.print_exc()
        sys.stderr.write(tb_text)
        sys.exit(1)
