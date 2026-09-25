# styles/__init__.py
# TJKEY 主题管理器
#
# 用法：
#   from styles import apply_theme, get_theme, DARK, LIGHT
#   apply_theme(app, "dark")   # 传入 QApplication 实例和主题名
#   apply_theme(app, "light")

from styles.dark import DARK_QSS
from styles.light import LIGHT_QSS

DARK = "dark"
LIGHT = "light"

# 当前主题（模块级变量，供其他模块查询）
_current_theme = DARK


def apply_theme(app, theme: str) -> None:
    """
    将主题样式表应用到整个应用程序。

    参数：
        app   - QApplication 实例
        theme - "dark" 或 "light"

    效果：
        立即生效，无需重启。
    """
    global _current_theme
    theme = theme.lower().strip()
    if theme not in (DARK, LIGHT):
        theme = DARK

    _current_theme = theme
    qss = DARK_QSS if theme == DARK else LIGHT_QSS
    app.setStyleSheet(qss)


def get_theme() -> str:
    """返回当前主题名称（"dark" 或 "light"）。"""
    return _current_theme


def is_dark() -> bool:
    """返回当前是否为深色主题。"""
    return _current_theme == DARK


def get_qss(theme: str = None) -> str:
    """
    获取指定主题的 QSS 字符串（不应用，只返回）。
    不传参数则返回当前主题的 QSS。
    """
    t = theme if theme else _current_theme
    return DARK_QSS if t == DARK else LIGHT_QSS


# 颜色常量（供 UI 模块动态绘图时使用，如 QPainter 绘制自定义控件）
COLORS = {
    DARK: {
        # Spotify 风格极深黑 + 金色强调
        "bg_primary":       "#121212",   # 最深背景
        "bg_secondary":     "#181818",   # 侧边栏/面板
        "bg_tertiary":      "#1f1f1f",   # 卡片/输入框
        "bg_hover":         "#2a2a2a",   # 悬停态
        "bg_selected":      "#2a2a2a",   # 选中态
        "bg_input":         "#1f1f1f",   # 输入框背景

        "text_primary":     "#ffffff",   # 主文字
        "text_secondary":   "#b3b3b3",   # 次要文字
        "text_hint":        "#6a6a6a",   # 提示文字
        "text_disabled":    "#4d4d4d",   # 禁用文字

        "accent":           "#f5a623",   # 金色强调
        "accent_hover":     "#f7b84e",   # 金色悬停

        "success":          "#1ed760",   # 绿色成功
        "warning":          "#ffa42b",   # 橙色警告
        "danger":           "#f3727f",   # 红色危险
        "danger_dark":      "#c0566e",   # 深红

        "border":           "#3a3a3a",   # 标准边框
        "border_light":     "#4d4d4d",   # 亮边框

        "secret_mask":      "#4d4d4d",   # 打码颜色
        "tag_bg":           "#2a2a2a",   # 标签背景
        "tag_text":         "#f5a623",   # 标签文字

        "expiry_green_bg":  "#0d2b1a",   # 到期绿背景
        "expiry_green_fg":  "#1ed760",   # 到期绿前景
        "expiry_yellow_bg": "#2b1f0a",   # 到期黄背景
        "expiry_yellow_fg": "#ffa42b",   # 到期黄前景
        "expiry_red_bg":    "#2b0d0f",   # 到期红背景
        "expiry_red_fg":    "#f3727f",   # 到期红前景

        "scrollbar":        "#3a3a3a",   # 滚动条
        "scrollbar_hover":  "#4d4d4d",   # 滚动条悬停
    },
    LIGHT: {
        # 干净白底 + 深金强调（浅色背景上的金色）
        "bg_primary":       "#f5f5f5",   # 主背景
        "bg_secondary":     "#efefef",   # 侧边栏/面板
        "bg_tertiary":      "#ffffff",   # 卡片/输入框
        "bg_hover":         "#eeeeee",   # 悬停态
        "bg_selected":      "#e5e5e5",   # 选中态
        "bg_input":         "#ffffff",   # 输入框背景

        "text_primary":     "#121212",   # 主文字
        "text_secondary":   "#6a6a6a",   # 次要文字
        "text_hint":        "#9a9a9a",   # 提示文字
        "text_disabled":    "#c0c0c0",   # 禁用文字

        "accent":           "#d4900f",   # 深金强调（浅色背景适配）
        "accent_hover":     "#e09e1a",   # 深金悬停

        "success":          "#1a8a3a",   # 绿色成功
        "warning":          "#b06000",   # 橙色警告
        "danger":           "#d20f39",   # 红色危险
        "danger_dark":      "#a00828",   # 深红

        "border":           "#e0e0e0",   # 标准边框
        "border_light":     "#eeeeee",   # 浅边框

        "secret_mask":      "#c0c0c0",   # 打码颜色
        "tag_bg":           "#eeeeee",   # 标签背景
        "tag_text":         "#d4900f",   # 标签文字

        "expiry_green_bg":  "#edf7ef",   # 到期绿背景
        "expiry_green_fg":  "#1a8a3a",   # 到期绿前景
        "expiry_yellow_bg": "#fff8ea",   # 到期黄背景
        "expiry_yellow_fg": "#b06000",   # 到期黄前景
        "expiry_red_bg":    "#fdecea",   # 到期红背景
        "expiry_red_fg":    "#d20f39",   # 到期红前景

        "scrollbar":        "#d8d8d8",   # 滚动条
        "scrollbar_hover":  "#b8b8b8",   # 滚动条悬停
    },
}


def color(key: str, theme: str = None) -> str:
    """
    获取指定主题的颜色值。

    用法：
        from styles import color
        c = color("accent")          # 当前主题的强调色
        c = color("danger", "light") # 浅色主题的危险色
    """
    t = theme if theme else _current_theme
    return COLORS.get(t, COLORS[DARK]).get(key, "#ff0000")
