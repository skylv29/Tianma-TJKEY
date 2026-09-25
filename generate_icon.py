# generate_icon.py
# TJKEY 图标生成脚本（一次性运行）
#
# 运行方式：python generate_icon.py
# 输出：assets/icon.png（256×256）和 assets/icon.ico（多尺寸）
#
# 图标设计：
#   - 深黑圆角矩形底色（#1a1a1a）
#   - 金色（#f5a623）锁形图案
#   - 右上角"TK"文字点缀
#
# 此脚本仅需运行一次，生成文件后即可删除。
# 如需更换为专业图标，直接将新的 icon.png / icon.ico 覆盖到 assets/ 即可。

import os
import sys
import math
import struct
import zlib

# 确保能找到 assets 目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# 纯 Python PNG 生成（无需 Pillow）
# ─────────────────────────────────────────────

def _pack_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """打包 PNG chunk。"""
    c = chunk_type + data
    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)


def _write_png(filename: str, pixels: list, width: int, height: int):
    """
    将像素数据写入 PNG 文件。
    pixels: list of (R, G, B, A) tuples, row-major
    """
    raw_rows = []
    for y in range(height):
        row = bytearray()
        row.append(0)  # filter type: None
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            row += bytes([r, g, b, a])
        raw_rows.append(bytes(row))

    raw_data = b"".join(raw_rows)
    compressed = zlib.compress(raw_data, 9)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2 | 4, 0, 0, 0)  # RGBA
    # 修正 IHDR: bit depth=8, colortype=6(RGBA)
    ihdr_data = struct.pack(">II", width, height) + bytes([8, 6, 0, 0, 0])

    chunks = (
        signature
        + _pack_chunk(b"IHDR", ihdr_data)
        + _pack_chunk(b"IDAT", compressed)
        + _pack_chunk(b"IEND", b"")
    )
    with open(filename, "wb") as f:
        f.write(chunks)


# ─────────────────────────────────────────────
# 图标绘制函数
# ─────────────────────────────────────────────

def _lerp(a, b, t):
    return a + (b - a) * t


def _clamp(v, lo=0, hi=255):
    return max(lo, min(hi, int(v)))


def _alpha_blend(fg_r, fg_g, fg_b, fg_a, bg_r, bg_g, bg_b):
    """将前景色（带 alpha）叠加到背景色上。"""
    a = fg_a / 255.0
    return (
        _clamp(fg_r * a + bg_r * (1 - a)),
        _clamp(fg_g * a + bg_g * (1 - a)),
        _clamp(fg_b * a + bg_b * (1 - a)),
    )


def _sdf_roundrect(px, py, cx, cy, hw, hh, r):
    """有符号距离场：圆角矩形，返回负值表示在内部。"""
    dx = max(abs(px - cx) - hw + r, 0)
    dy = max(abs(py - cy) - hh + r, 0)
    return math.sqrt(dx * dx + dy * dy) - r


def _sdf_circle(px, py, cx, cy, radius):
    """有符号距离场：圆形。"""
    dx = px - cx
    dy = py - cy
    return math.sqrt(dx * dx + dy * dy) - radius


def _smooth(d, aa=1.0):
    """抗锯齿平滑函数，返回 0-255 的覆盖值。"""
    return _clamp((0.5 - d / aa) * 255, 0, 255)


def draw_icon(size: int) -> list:
    """
    绘制 TJKEY 图标，返回 RGBA 像素列表。

    设计：
      - 深黑（#1a1a1a）圆角矩形背景
      - 金色（#f5a623）锁形：下方矩形锁体 + 上方 U 形锁梁
      - 锁孔：黑色小圆
    """
    pixels = [(0, 0, 0, 0)] * (size * size)

    s = size
    cx = s / 2
    cy = s / 2

    # 颜色定义
    BG_R, BG_G, BG_B = 0x1a, 0x1a, 0x1a      # 背景深黑
    GOLD_R, GOLD_G, GOLD_B = 0xf5, 0xa6, 0x23  # 金色
    DARK_R, DARK_G, DARK_B = 0x0a, 0x0a, 0x0a  # 锁孔深色

    # 背景圆角矩形参数（留 4% 边距）
    margin = s * 0.04
    bg_hw = s / 2 - margin
    bg_hh = s / 2 - margin
    bg_r  = s * 0.18   # 圆角半径

    # 锁体参数（下方矩形）
    body_w  = s * 0.50
    body_h  = s * 0.34
    body_cx = cx
    body_cy = cy + s * 0.10
    body_r  = s * 0.07

    # 锁梁参数（U 形弧）
    shackle_outer_r = s * 0.22
    shackle_inner_r = s * 0.13
    shackle_cx = cx
    shackle_cy = cy - s * 0.06   # 圆心略高于锁体顶部
    shackle_bottom_y = body_cy - body_h / 2  # 锁梁进入锁体的位置

    # 锁孔参数
    hole_r = s * 0.055
    hole_cx = cx
    hole_cy = body_cy + s * 0.01

    for y in range(s):
        for x in range(s):
            px, py = x + 0.5, y + 0.5

            # 1. 背景圆角矩形
            d_bg = _sdf_roundrect(px, py, cx, cy, bg_hw, bg_hh, bg_r)
            bg_a = _smooth(d_bg, 1.2)
            if bg_a == 0:
                pixels[y * s + x] = (0, 0, 0, 0)
                continue

            r, g, b = BG_R, BG_G, BG_B

            # 2. 锁梁（U 形）：用外圆 - 内圆，且只保留上半部分
            in_shackle = False
            if py < shackle_bottom_y + s * 0.04:  # 只在锁体上方绘制
                d_outer = _sdf_circle(px, py, shackle_cx, shackle_cy, shackle_outer_r)
                d_inner = _sdf_circle(px, py, shackle_cx, shackle_cy, shackle_inner_r)
                # 在外圆内且在内圆外 = 环形区域
                if d_outer <= 0 and d_inner >= 0:
                    in_shackle = True

            # 锁梁两侧竖杆延伸到锁体
            left_bar_x  = shackle_cx - (shackle_outer_r + shackle_inner_r) / 2
            right_bar_x = shackle_cx + (shackle_outer_r + shackle_inner_r) / 2
            bar_half_w  = (shackle_outer_r - shackle_inner_r) / 2

            if (abs(px - left_bar_x) < bar_half_w or
                    abs(px - right_bar_x) < bar_half_w):
                if shackle_cy <= py <= shackle_bottom_y + s * 0.04:
                    in_shackle = True

            if in_shackle:
                r, g, b = GOLD_R, GOLD_G, GOLD_B

            # 3. 锁体矩形
            d_body = _sdf_roundrect(px, py, body_cx, body_cy,
                                    body_w / 2, body_h / 2, body_r)
            body_a = _smooth(d_body, 1.2)
            if body_a > 0:
                gold_a = body_a
                r, g, b = _alpha_blend(GOLD_R, GOLD_G, GOLD_B, gold_a, r, g, b)

            # 4. 锁孔（黑色圆形）
            d_hole = _sdf_circle(px, py, hole_cx, hole_cy, hole_r)
            hole_a = _smooth(d_hole, 1.0)
            if hole_a > 0:
                r, g, b = _alpha_blend(DARK_R, DARK_G, DARK_B, hole_a, r, g, b)

            pixels[y * s + x] = (
                _clamp(r), _clamp(g), _clamp(b), bg_a
            )

    return pixels


# ─────────────────────────────────────────────
# ICO 文件生成
# ─────────────────────────────────────────────

def _pixels_to_bmp_data(pixels: list, size: int) -> bytes:
    """将像素转换为 ICO 内嵌的 BMP 数据（32bpp BGRA，倒序行）。"""
    # BITMAPINFOHEADER（40字节），高度×2 是 ICO 格式要求
    header = struct.pack(
        "<IiiHHIIiiII",
        40,          # 头大小
        size,        # 宽度
        size * 2,    # 高度（×2，ICO 格式要求）
        1,           # 颜色平面数
        32,          # 位深度
        0,           # 压缩方式（无）
        size * size * 4,  # 图像大小
        0, 0,        # 水平/垂直分辨率
        0, 0,        # 颜色表条目数
    )

    # 像素数据（BGRA 格式，从底部行开始）
    pixel_data = bytearray()
    for y in range(size - 1, -1, -1):  # 倒序行
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            pixel_data += bytes([b, g, r, a])  # BGRA

    # AND mask（全0，使用 alpha 通道）
    and_mask = bytes(((size + 31) // 32) * 4 * size)

    return header + bytes(pixel_data) + and_mask


def _pixels_to_png_bytes(pixels: list, size: int) -> bytes:
    """将像素转换为 PNG 字节流（用于 ICO 内嵌 PNG）。"""
    import io

    raw_rows = []
    for y in range(size):
        row = bytearray([0])  # filter: None
        for x in range(size):
            r, g, b, a = pixels[y * size + x]
            row += bytes([r, g, b, a])
        raw_rows.append(bytes(row))

    raw_data = b"".join(raw_rows)
    compressed = zlib.compress(raw_data, 9)

    ihdr_data = struct.pack(">II", size, size) + bytes([8, 6, 0, 0, 0])

    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _pack_chunk(b"IHDR", ihdr_data)
        + _pack_chunk(b"IDAT", compressed)
        + _pack_chunk(b"IEND", b"")
    )
    return png_bytes


def write_ico(filename: str, sizes=(16, 32, 48, 256)):
    """生成包含多尺寸的 ICO 文件。"""
    images = []
    for size in sizes:
        pixels = draw_icon(size)
        if size == 256:
            # 256px 用 PNG 格式内嵌（ICO 标准）
            data = _pixels_to_png_bytes(pixels, size)
            images.append((size, data, True))  # True = PNG
        else:
            data = _pixels_to_bmp_data(pixels, size)
            images.append((size, data, False))  # False = BMP

    # ICO 文件头
    ico_header = struct.pack("<HHH", 0, 1, len(images))  # Reserved, Type=1(ICO), Count

    # 目录条目（每个 16 字节）
    offset = 6 + len(images) * 16  # 头部 + 目录
    entries = b""
    for size, data, is_png in images:
        w = 0 if size == 256 else size   # ICO 格式：256 写 0
        h = 0 if size == 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            w, h,       # 宽高
            0,          # 颜色数（0=truecolor）
            0,          # 保留
            1,          # 颜色平面数
            32,         # 位深度
            len(data),  # 数据大小
            offset,     # 数据偏移
        )
        offset += len(data)

    ico_data = ico_header + entries
    for _, data, _ in images:
        ico_data += data

    with open(filename, "wb") as f:
        f.write(ico_data)


def write_png_file(filename: str, size: int = 256):
    """生成 PNG 图标文件。"""
    pixels = draw_icon(size)
    png_bytes = _pixels_to_png_bytes(pixels, size)
    with open(filename, "wb") as f:
        f.write(png_bytes)


# ─────────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("TJKEY 图标生成脚本")
    print(f"输出目录：{ASSETS_DIR}")
    print()

    # 生成 PNG（256×256）
    png_path = os.path.join(ASSETS_DIR, "icon.png")
    print("正在生成 icon.png（256×256）...", end=" ", flush=True)
    write_png_file(png_path, 256)
    print(f"✓  {png_path}")

    # 生成 ICO（多尺寸）
    ico_path = os.path.join(ASSETS_DIR, "icon.ico")
    print("正在生成 icon.ico（16/32/48/256px）...", end=" ", flush=True)
    write_ico(ico_path, sizes=(16, 32, 48, 256))
    print(f"✓  {ico_path}")

    print()
    print("图标生成完成！")
    print("如需更换为专业图标，直接覆盖 assets/ 下的两个文件即可。")
    print()

    # 验证文件大小
    for path in [png_path, ico_path]:
        size_kb = os.path.getsize(path) / 1024
        print(f"  {os.path.basename(path)}：{size_kb:.1f} KB")
