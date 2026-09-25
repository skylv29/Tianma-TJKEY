# icons.py
# TJKEY 图标系统
#
# 基于 Feather Icons（MIT 开源，https://feathericons.com）
# 所有图标使用统一的 2px 描边，线条风格一致。
#
# 使用方式：
#   from icons import icon, expiry_dot
#
#   # 获取 QIcon（用于按钮 setIcon）
#   btn.setIcon(icon("lock", color="#f5a623", size=16))
#
#   # 获取 QPixmap（用于 QLabel setPixmap）
#   lbl.setPixmap(icon("folder").pixmap(20, 20))
#
#   # 到期提醒彩色圆点 QPixmap
#   dot = expiry_dot("red", size=10)
#
# 图标命名对照：
#   lock          锁形（登录/锁屏）
#   unlock        开锁
#   eye           显示密码
#   eye-off       隐藏密码
#   copy          复制
#   check         复制成功 ✓
#   edit          编辑（铅笔）
#   trash         删除
#   settings      设置（齿轮）
#   upload        导出
#   folder        大类
#   folder-open   展开的大类
#   layers        所有条目
#   inbox         未分类
#   plus          新建/添加
#   x             关闭/删除行
#   chevron-up    向上
#   chevron-down  向下
#   external-link URL 打开
#   alert-circle  警告/错误
#   calendar      日期字段
#   tag           标签
#   search        搜索
#   user          用户名字段
#   key           密码字段
#   globe         网址字段
#   shield        安全

import os
from functools import lru_cache

from PySide6.QtCore import Qt, QByteArray, QSize, QRectF, QPointF
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QBrush,
    QPainterPath,
)
from PySide6.QtSvg import QSvgRenderer


# ─────────────────────────────────────────────
# Feather Icons SVG 路径数据
# 每个图标统一使用 24×24 viewBox，2px 描边
# ─────────────────────────────────────────────

# SVG 模板：统一 viewBox 24×24，stroke-width 2，round linecap/linejoin
_SVG_TMPL = """<svg xmlns="http://www.w3.org/2000/svg"
  width="{size}" height="{size}" viewBox="0 0 24 24"
  fill="none" stroke="{color}"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  {paths}
</svg>"""

# 所有图标的路径数据（纯 <path>/<circle>/<rect>/<line>/<polyline> 元素）
_ICON_PATHS: dict[str, str] = {

    # 锁形（登录界面 Logo / 锁屏按钮）
    "lock": """
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>""",

    # 开锁
    "unlock": """
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 9.9-1"/>""",

    # 眼睛（显示密码）
    "eye": """
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
        <circle cx="12" cy="12" r="3"/>""",

    # 眼睛划线（隐藏密码）
    "eye-off": """
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8
                 a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24
                 A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8
                 a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07
                 a3 3 0 1 1-4.24-4.24"/>
        <line x1="1" y1="1" x2="23" y2="23"/>""",

    # 复制
    "copy": """
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>""",

    # 勾（复制成功提示）
    "check": """
        <polyline points="20 6 9 17 4 12"/>""",

    # 铅笔（编辑）
    "edit": """
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>""",

    # 垃圾桶（删除）
    "trash": """
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
        <path d="M10 11v6"/>
        <path d="M14 11v6"/>
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>""",

    # 齿轮（设置）
    "settings": """
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1
                 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33
                 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09
                 A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06
                 a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06
                 A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3
                 a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9
                 a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83
                 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68
                 a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09
                 a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06
                 a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06
                 A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21
                 a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>""",

    # 上传/导出（向上箭头出盒子）
    "upload": """
        <polyline points="16 16 12 12 8 16"/>
        <line x1="12" y1="12" x2="12" y2="21"/>
        <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>""",

    # 文件夹（大类）
    "folder": """
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>""",

    # 打开的文件夹（展开大类）
    "folder-open": """
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        <polyline points="9 16 12 19 15 16"/>
        <line x1="12" y1="12" x2="12" y2="19"/>""",

    # 图层（所有条目）
    "layers": """
        <polygon points="12 2 2 7 12 12 22 7 12 2"/>
        <polyline points="2 17 12 22 22 17"/>
        <polyline points="2 12 12 17 22 12"/>""",

    # 收件箱（未分类）
    "inbox": """
        <polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>
        <path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89
                 A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>""",

    # 加号（新建/添加字段）
    "plus": """
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>""",

    # X（关闭/删除行）
    "x": """
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>""",

    # 向上箭头（排序上移）
    "chevron-up": """
        <polyline points="18 15 12 9 6 15"/>""",

    # 向下箭头（排序下移）
    "chevron-down": """
        <polyline points="6 9 12 15 18 9"/>""",

    # 向右箭头
    "chevron-right": """
        <polyline points="9 18 15 12 9 6"/>""",

    # 外部链接（URL 打开）
    "external-link": """
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        <polyline points="15 3 21 3 21 9"/>
        <line x1="10" y1="14" x2="21" y2="3"/>""",

    # 警告圆圈（错误提示）
    "alert-circle": """
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>""",

    # 日历（日期字段）
    "calendar": """
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
        <line x1="16" y1="2" x2="16" y2="6"/>
        <line x1="8" y1="2" x2="8" y2="6"/>
        <line x1="3" y1="10" x2="21" y2="10"/>""",

    # 标签（标签字段）
    "tag": """
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59
                 a2 2 0 0 1 0 2.82z"/>
        <line x1="7" y1="7" x2="7.01" y2="7"/>""",

    # 搜索（搜索栏）
    "search": """
        <circle cx="11" cy="11" r="8"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65"/>""",

    # 用户（用户名字段）
    "user": """
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>""",

    # 钥匙（密码/secret 字段）
    "key": """
        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778
                 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>""",

    # 地球（网址字段）
    "globe": """
        <circle cx="12" cy="12" r="10"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10
                 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>""",

    # 盾牌（安全/密保）
    "shield": """
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>""",

    # 链接（URL 前缀图标）
    "link": """
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>""",

    # 刷新（重置/恢复）
    "refresh": """
        <polyline points="23 4 23 10 17 10"/>
        <polyline points="1 20 1 14 7 14"/>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36
                 A9 9 0 0 0 20.49 15"/>""",

    # 信息（提示/说明）
    "info": """
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="16" x2="12" y2="12"/>
        <line x1="12" y1="8" x2="12.01" y2="8"/>""",

    # 登出（退出登录）
    "log-out": """
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <polyline points="16 17 21 12 16 7"/>
        <line x1="21" y1="12" x2="9" y2="12"/>""",

    # 下载（导入）
    "download": """
        <polyline points="8 17 12 21 16 17"/>
        <line x1="12" y1="12" x2="12" y2="21"/>
        <path d="M20.88 18.09A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.29"/>""",

    # 菜单（汉堡菜单）
    "menu": """
        <line x1="3" y1="12" x2="21" y2="12"/>
        <line x1="3" y1="6" x2="21" y2="6"/>
        <line x1="3" y1="18" x2="21" y2="18"/>""",

    # 更多（三个点）
    "more-horizontal": """
        <circle cx="12" cy="12" r="1"/>
        <circle cx="19" cy="12" r="1"/>
        <circle cx="5" cy="12" r="1"/>""",

    # 太阳（浅色主题图标）
    "sun": """
        <circle cx="12" cy="12" r="5"/>
        <line x1="12" y1="1" x2="12" y2="3"/>
        <line x1="12" y1="21" x2="12" y2="23"/>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
        <line x1="1" y1="12" x2="3" y2="12"/>
        <line x1="21" y1="12" x2="23" y2="12"/>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>""",

    # 月亮（深色主题图标）
    "moon": """
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>""",
}


# ─────────────────────────────────────────────
# 核心渲染函数
# ─────────────────────────────────────────────

def _render_svg(name: str, color: str, size: int) -> QPixmap:
    """
    将 SVG 路径数据渲染为 QPixmap。

    参数：
        name  - 图标名称（见 _ICON_PATHS）
        color - 描边颜色，CSS 十六进制字符串如 "#f5a623"
        size  - 输出像素尺寸（宽高相等）

    返回：
        size×size 的透明背景 QPixmap
    """
    paths = _ICON_PATHS.get(name)
    if paths is None:
        # 未知图标：返回空 pixmap
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm

    svg_bytes = _SVG_TMPL.format(
        size=24,
        color=color,
        paths=paths.strip(),
    ).encode("utf-8")

    renderer = QSvgRenderer(QByteArray(svg_bytes))

    # 高 DPI：渲染到 2× 再缩放
    render_size = size * 2
    pm = QPixmap(render_size, render_size)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, render_size, render_size))
    painter.end()

    return pm.scaled(size, size,
                     Qt.KeepAspectRatio,
                     Qt.SmoothTransformation)


# ─────────────────────────────────────────────
# 公开接口：icon()
# ─────────────────────────────────────────────

def icon(name: str,
         color: str = None,
         size: int = 16,
         theme: str = None) -> QIcon:
    """
    获取指定图标的 QIcon（用于按钮 setIcon / QLabel setPixmap 等）。

    参数：
        name  - 图标名称，如 "lock"、"copy"、"settings"
        color - 描边颜色；None 时根据当前主题自动选择
                  深色主题 → #b3b3b3（次文字色，静默态）
                  浅色主题 → #6a6a6a
        size  - 图标像素尺寸，默认 16
        theme - 强制指定主题 "dark"/"light"；None 时自动读取当前主题

    返回：
        QIcon 对象，可直接传给 setIcon()
    """
    if color is None:
        from styles import get_theme, color as theme_color
        t = theme or get_theme()
        color = theme_color("text_secondary", t)

    pm = _render_svg(name, color, size)
    return QIcon(pm)


def pixmap(name: str,
           color: str = None,
           size: int = 16,
           theme: str = None) -> QPixmap:
    """
    获取指定图标的 QPixmap（直接用于 QLabel.setPixmap）。

    参数同 icon()，返回 QPixmap 而非 QIcon。
    """
    if color is None:
        from styles import get_theme, color as theme_color
        t = theme or get_theme()
        color = theme_color("text_secondary", t)
    return _render_svg(name, color, size)


def accent_icon(name: str, size: int = 16) -> QIcon:
    """
    获取强调色（金色）版本的图标，用于高亮状态、主操作等。
    自动根据当前主题选择 accent 颜色。
    """
    from styles import get_theme, color as theme_color
    c = theme_color("accent", get_theme())
    return icon(name, color=c, size=size)


def danger_icon(name: str, size: int = 16) -> QIcon:
    """获取危险色（红色）版本的图标，用于删除等危险操作。"""
    from styles import get_theme, color as theme_color
    c = theme_color("danger", get_theme())
    return icon(name, color=c, size=size)


def white_icon(name: str, size: int = 16) -> QIcon:
    """获取白色图标，用于主按钮（金色背景上）。"""
    return icon(name, color="#ffffff", size=size)


def dark_icon(name: str, size: int = 16) -> QIcon:
    """获取深色图标，用于浅色主题的主按钮（金色背景上）。"""
    return icon(name, color="#121212", size=size)


# ─────────────────────────────────────────────
# 公开接口：expiry_dot()
# ─────────────────────────────────────────────

def expiry_dot(level: str, size: int = 10) -> QPixmap:
    """
    绘制到期提醒的彩色实心圆点（替代 🟢🟡🔴 Emoji）。

    参数：
        level - "green" / "yellow" / "red"
        size  - 圆点直径像素数，默认 10

    返回：
        size×size 的 QPixmap，透明背景 + 实心圆
    """
    # 颜色映射（固定色值，不随主题变化，语义颜色）
    COLOR_MAP = {
        "green":  "#1ed760",
        "yellow": "#ffa42b",
        "red":    "#f3727f",
    }
    dot_color = COLOR_MAP.get(level, "#6a6a6a")

    # 渲染 2× 再缩放（抗锯齿）
    render_size = size * 2
    pm = QPixmap(render_size, render_size)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setBrush(QBrush(QColor(dot_color)))
    painter.setPen(Qt.NoPen)

    margin = render_size * 0.08
    painter.drawEllipse(
        QRectF(margin, margin,
               render_size - 2 * margin,
               render_size - 2 * margin)
    )
    painter.end()

    return pm.scaled(size, size,
                     Qt.KeepAspectRatio,
                     Qt.SmoothTransformation)


def expiry_dot_icon(level: str, size: int = 10) -> QIcon:
    """expiry_dot() 的 QIcon 版本。"""
    return QIcon(expiry_dot(level, size))


# ─────────────────────────────────────────────
# 便利函数：为 QLabel 设置图标（常用模式封装）
# ─────────────────────────────────────────────

def set_icon_label(label, name: str, color: str = None, size: int = 16):
    """
    将图标设置到 QLabel 上（替代 setText("🔐") 等 Emoji 用法）。

    用法：
        set_icon_label(self.icon_lbl, "lock", size=20)
    """
    label.setPixmap(pixmap(name, color=color, size=size))
    label.setFixedSize(size, size)
    label.setScaledContents(True)


def set_button_icon(button, name: str, color: str = None, size: int = 16):
    """
    将图标设置到 QPushButton 上，同时清空文字。

    用法（纯图标按钮）：
        set_button_icon(self.edit_btn, "edit", size=16)

    如需图标+文字，建议用 button.setIcon(icon(...)) 并保留 setText()。
    """
    button.setIcon(icon(name, color=color, size=size))
    button.setIconSize(QSize(size, size))


# ─────────────────────────────────────────────
# 模块自测
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import (
        QApplication, QWidget, QGridLayout,
        QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    )

    app = QApplication(sys.argv)

    # 加载主题
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from styles import apply_theme, DARK
    apply_theme(app, DARK)

    win = QWidget()
    win.setWindowTitle("TJKEY Icons 预览")
    win.setMinimumSize(760, 520)

    main_layout = QVBoxLayout(win)
    main_layout.setSpacing(16)
    main_layout.setContentsMargins(24, 24, 24, 24)

    title = QLabel("图标系统预览（深色主题）")
    title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
    main_layout.addWidget(title)

    # 图标网格
    grid_widget = QWidget()
    grid = QGridLayout(grid_widget)
    grid.setSpacing(12)
    grid.setContentsMargins(0, 0, 0, 0)

    all_icons = list(_ICON_PATHS.keys())
    cols = 8

    for idx, name in enumerate(all_icons):
        row, col = divmod(idx, cols)

        cell = QFrame()
        cell.setStyleSheet(
            "QFrame { background:#181818; border-radius:8px; }"
            "QFrame:hover { background:#2a2a2a; }"
        )
        cell_layout = QVBoxLayout(cell)
        cell_layout.setSpacing(4)
        cell_layout.setContentsMargins(10, 10, 10, 10)
        cell_layout.setAlignment(Qt.AlignCenter)

        # 图标（默认次文字色）
        icon_lbl = QLabel()
        pm = pixmap(name, color="#b3b3b3", size=24)
        icon_lbl.setPixmap(pm)
        icon_lbl.setAlignment(Qt.AlignCenter)
        cell_layout.addWidget(icon_lbl)

        # 名称
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size:10px; color:#6a6a6a;")
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        cell_layout.addWidget(name_lbl)

        grid.addWidget(cell, row, col)

    main_layout.addWidget(grid_widget)

    # 颜色变体展示行
    variants_lbl = QLabel("颜色变体：默认 / 金色强调 / 危险红 / 白色")
    variants_lbl.setStyleSheet("font-size:13px; color:#b3b3b3; margin-top:8px;")
    main_layout.addWidget(variants_lbl)

    variants_row = QHBoxLayout()
    variants_row.setSpacing(16)

    for variant_name, color_val, bg in [
        ("默认（次文字）", "#b3b3b3", "#181818"),
        ("金色强调",        "#f5a623", "#181818"),
        ("危险红",          "#f3727f", "#181818"),
        ("白色",            "#ffffff", "#282828"),
    ]:
        v_frame = QFrame()
        v_frame.setStyleSheet(f"QFrame{{background:{bg};border-radius:8px;padding:8px;}}")
        v_layout = QHBoxLayout(v_frame)
        v_layout.setSpacing(8)

        for iname in ["lock", "edit", "copy", "trash", "settings"]:
            lbl = QLabel()
            lbl.setPixmap(pixmap(iname, color=color_val, size=20))
            v_layout.addWidget(lbl)

        caption = QLabel(variant_name)
        caption.setStyleSheet(f"color:{color_val};font-size:11px;")
        v_layout.addWidget(caption)

        variants_row.addWidget(v_frame)

    main_layout.addLayout(variants_row)

    # 到期圆点展示
    dot_lbl = QLabel("到期圆点：")
    dot_lbl.setStyleSheet("font-size:13px; color:#b3b3b3; margin-top:4px;")
    main_layout.addWidget(dot_lbl)

    dot_row = QHBoxLayout()
    for level, label_text in [("green","绿色（>90天）"),
                                ("yellow","黄色（30-90天）"),
                                ("red","红色（<30天）")]:
        d_frame = QFrame()
        d_frame.setStyleSheet("QFrame{background:#181818;border-radius:8px;padding:8px;}")
        d_layout = QHBoxLayout(d_frame)
        d_layout.setSpacing(8)

        for sz in [8, 10, 12, 14]:
            dot_widget = QLabel()
            dot_widget.setPixmap(expiry_dot(level, sz))
            d_layout.addWidget(dot_widget)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("color:#b3b3b3;font-size:11px;")
        d_layout.addWidget(lbl)
        dot_row.addWidget(d_frame)

    main_layout.addLayout(dot_row)
    main_layout.addStretch()

    win.show()
    print(f"图标总数：{len(_ICON_PATHS)}")
    print("所有图标名称：")
    for name in sorted(_ICON_PATHS.keys()):
        print(f"  {name}")

    sys.exit(app.exec())
