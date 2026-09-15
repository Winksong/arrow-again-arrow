"""绘制层：棋盘、箭头、状态栏、结果卡片、动画。

约定：
    - 中文字体按 **字体文件路径** 加载并加兜底，
      不要用 pygame.font.SysFont 枚举系统字体（可能 TypeError 崩溃）。
    - 结果面板使用**不透明圆角卡片** + 卡片内相对定位，
      避免半透明遮罩导致文字与棋盘重叠。
"""

from __future__ import annotations

import math
from pathlib import Path

import pygame

from .model import BLOCKED, Arrow, Board

# 动画时长（秒）
FLY_DURATION = 0.36
SHAKE_DURATION = 0.42

# 配色与字号
# --------------------------------------------------------------------------

# 四个方向用四种颜色区分
DIR_COLORS: dict[str, tuple[int, int, int]] = {
    "up": (255, 202, 40),      # 黄
    "down": (255, 145, 0),     # 橙
    "left": (102, 187, 106),   # 绿
    "right": (66, 165, 245),   # 蓝
}

BG_TOP = (28, 32, 44)
BG_BOTTOM = (18, 20, 28)
GRID_BG = (44, 50, 66)
GRID_LINE = (62, 70, 90)
CARD_BG = (52, 60, 80)          # 结果卡片：不透明
CARD_BORDER = (90, 102, 130)
TEXT_MAIN = (236, 240, 248)
TEXT_DIM = (150, 162, 186)
DANGER = (239, 83, 80)
OK_COLOR = (102, 187, 106)

# 中文字体候选（按优先级）
FONT_CANDIDATES: list[Path] = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),      # 微软雅黑
    Path(r"C:\Windows\Fonts\msyhl.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),    # 黑体
    Path(r"C:\Windows\Fonts\simsun.ttc"),    # 宋体
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
]


# --------------------------------------------------------------------------
# 字体加载（带兜底，绝不因字体问题崩溃）
# --------------------------------------------------------------------------

_font_cache: dict[tuple[str, int], pygame.font.Font] = {}


def load_font(size: int, bold: bool = False, kind: str = "text") -> pygame.font.Font:
    """按字体文件路径加载中文字体，失败时逐级降级。

    降级顺序：候选字体文件 → pygame 自带默认字体。
    全程不调用 SysFont，避免枚举系统字体触发
    `TypeError: expected str, bytes or os.PathLike object, not int`。
    """
    key = (f"{kind}-{'b' if bold else 'n'}", size)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    candidates: list[Path] = []
    if kind == "symbol":
        # 箭头符号优先用这几款，字形更接近
        candidates += [
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
            Path(r"C:\Windows\Fonts\seguisym.ttf"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
        ]
    candidates += FONT_CANDIDATES

    font: pygame.font.Font | None = None
    for path in candidates:
        try:
            if path.exists():
                font = pygame.font.Font(str(path), size)
                break
        except (OSError, pygame.error):
            continue

    if font is None:
        # 最后兜底：pygame 内置字体（不含中文，但至少不崩）
        font = pygame.font.Font(None, size)

    if bold:
        try:
            font.set_bold(True)
        except pygame.error:
            pass

    _font_cache[key] = font
    return font


def clear_font_cache() -> None:
    """字体缓存需在 pygame.quit() 后清理，否则复用已失效的字体对象。"""
    _font_cache.clear()


# --------------------------------------------------------------------------
# 基础绘制工具
# --------------------------------------------------------------------------

def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                      bottom: tuple[int, int, int]) -> pygame.Surface:
    """生成竖直渐变背景。逐行绘制，只在初始化时做一次。"""
    w, h = size
    surf = pygame.Surface(size)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(surf, color, (0, y), (w, y))
    return surf


def draw_arrow_glyph(surface: pygame.Surface, center: tuple[int, int], radius: int,
                     direction: str, color: tuple[int, int, int],
                     angle: float = 0.0) -> None:
    """在 center 处画一个指向 direction 的箭头（纯几何绘制，不依赖字形）。

    做法：先画一个正三角形（默认朝上），再按方向旋转。
    angle 为额外旋转量，用于被阻挡时的晃动。
    """
    base_angle = {"up": 0, "right": 90, "down": 180, "left": 270}[direction]
    rot = math.radians(base_angle + angle)

    # 三角形三点（局部坐标，尖端朝上）
    pts = [
        (0.0, -radius),            # 尖端
        (-radius * 0.78, radius * 0.62),
        (radius * 0.78, radius * 0.62),
    ]
    rotated: list[tuple[float, float]] = []
    for x, y in pts:
        rotated.append((
            center[0] + x * math.cos(rot) - y * math.sin(rot),
            center[1] + x * math.sin(rot) + y * math.cos(rot),
        ))
    pygame.draw.polygon(surface, color, rotated)
    # 描一圈深色边，提升对比度
    pygame.draw.polygon(surface, (18, 20, 28), rotated, width=2)


def draw_arrow_badge(surface: pygame.Surface, rect: pygame.Rect, arrow: Arrow,
                     shake_offset: int = 0, highlight: bool = False) -> None:
    """画一个箭头徽章：圆角底板 + 阴影 + 箭头图形。

    shake_offset 为被阻挡晃动时的水平偏移。
    """
    color = DIR_COLORS[arrow.direction]
    if arrow.state == BLOCKED:
        color = DANGER

    r = rect.move(shake_offset, 0)
    radius = max(8, r.height // 5)

    # 阴影
    shadow = r.move(0, 3)
    pygame.draw.rect(surface, (14, 16, 22), shadow, border_radius=radius)
    # 底板
    pygame.draw.rect(surface, GRID_BG, r, border_radius=radius)
    # 高光边框
    border = color if highlight else GRID_LINE
    pygame.draw.rect(surface, border, r, width=2, border_radius=radius)

    draw_arrow_glyph(
        surface,
        (r.centerx, r.centery),
        int(r.height * 0.26),
        arrow.direction,
        color,
    )


# --------------------------------------------------------------------------
# 棋盘布局：屏幕坐标 ↔ 格子坐标
# --------------------------------------------------------------------------

class BoardLayout:
    """负责棋盘在窗口中的位置计算，以及屏幕坐标 ↔ 格子坐标换算。

    把换算集中在这里，测试才能按「格子中心像素坐标」投递鼠标事件。
    """

    def __init__(self, rows: int, cols: int, area: pygame.Rect, gap: int = 8) -> None:
        self.rows = rows
        self.cols = cols
        self.area = area
        self.gap = gap

        cell_w = (area.width - gap * (cols - 1)) // cols
        cell_h = (area.height - gap * (rows - 1)) // rows
        self.cell = min(cell_w, cell_h)

        total_w = self.cell * cols + gap * (cols - 1)
        total_h = self.cell * rows + gap * (rows - 1)
        self.origin_x = area.x + (area.width - total_w) // 2
        self.origin_y = area.y + (area.height - total_h) // 2

    def cell_rect(self, r: int, c: int) -> pygame.Rect:
        return pygame.Rect(
            self.origin_x + c * (self.cell + self.gap),
            self.origin_y + r * (self.cell + self.gap),
            self.cell,
            self.cell,
        )

    def cell_center(self, r: int, c: int) -> tuple[int, int]:
        return self.cell_rect(r, c).center

    def to_cell(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """屏幕坐标 → 格子坐标；不在任何格子内则返回 None。

        用「反算 + 回验」两步：先按步长反推索引，再用 cell_rect 验证
        该点确实落在格子里（排除间隙与棋盘外）。
        """
        x, y = pos
        step = self.cell + self.gap

        c = (x - self.origin_x) // step
        r = (y - self.origin_y) // step
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return None
        if not self.cell_rect(r, c).collidepoint(pos):
            return None
        return int(r), int(c)


# --------------------------------------------------------------------------
# 棋盘绘制
# --------------------------------------------------------------------------

def draw_board(surface: pygame.Surface, board: Board, layout: BoardLayout,
               shake: dict[tuple[int, int], float] | None = None,
               hover: tuple[int, int] | None = None,
               flying: dict[Arrow, float] | None = None) -> None:
    """绘制棋盘网格与全部箭头。

    shake:  {(row, col): 像素偏移}，被阻挡时的晃动
    flying: {arrow: 已播放时长}，飞出动画（平移 + 淡出 + 残影）
    """
    shake = shake or {}
    flying = flying or {}

    # 棋盘底板
    pad = 14
    outer = pygame.Rect(
        layout.origin_x - pad,
        layout.origin_y - pad,
        layout.cell * layout.cols + layout.gap * (layout.cols - 1) + pad * 2,
        layout.cell * layout.rows + layout.gap * (layout.rows - 1) + pad * 2,
    )
    pygame.draw.rect(surface, (24, 28, 38), outer.move(0, 4), border_radius=18)
    pygame.draw.rect(surface, (34, 39, 53), outer, border_radius=18)
    pygame.draw.rect(surface, GRID_LINE, outer, width=2, border_radius=18)

    # 空格
    for r in range(layout.rows):
        for c in range(layout.cols):
            rect = layout.cell_rect(r, c)
            is_hover = hover == (r, c)
            fill = (56, 64, 84) if is_hover else (40, 45, 60)
            pygame.draw.rect(surface, fill, rect, border_radius=max(8, layout.cell // 5))

    # 箭头：先画静止的，再画飞出的（盖在最上层）
    static: list[Arrow] = []
    moving: list[Arrow] = []
    for arrow in board.arrows:
        (moving if arrow in flying else static).append(arrow)

    for arrow in static:
        rect = layout.cell_rect(arrow.row, arrow.col)
        draw_arrow_badge(
            surface, rect, arrow,
            shake_offset=int(shake.get((arrow.row, arrow.col), 0)),
            highlight=hover == (arrow.row, arrow.col),
        )

    for arrow in moving:
        _, offset, alpha = fly_transform(arrow, flying[arrow])
        # 残影：跟随在后、更淡
        for ghost_i, ghost_alpha in ((0.16, 0.28), (0.08, 0.5)):
            _, g_offset, _ = fly_transform(arrow, flying[arrow] * (1 - ghost_i))
            _blit_flying(surface, layout, arrow, g_offset, alpha * ghost_alpha)
        _blit_flying(surface, layout, arrow, offset, alpha)


def fly_transform(arrow: Arrow, t_sec: float) -> tuple[float, tuple[float, float], float]:
    """飞出动画的插值：返回 (进度, 像素偏移, 不透明度 0~1)。

    带轻微加速（t**1.35），观感比匀速自然。
    """
    p = min(t_sec / FLY_DURATION, 1.0)
    eased = p ** 1.35

    dr, dc = arrow.delta
    step = 74.0                      # 每个格子的位移像素
    offset = (dc * step * eased * 2.2, dr * step * eased * 2.2)

    # 前 25% 保持不透明，之后淡出
    alpha = 1.0 if p < 0.25 else max(1.0 - (p - 0.25) / 0.75, 0.0)
    return p, offset, alpha


def _blit_flying(surface: pygame.Surface, layout: BoardLayout, arrow: Arrow,
                 offset: tuple[float, float], alpha: float) -> None:
    """把飞出中的箭头绘制到临时表面再整体平移 + 淡出。"""
    if alpha <= 0.02:
        return
    cell = layout.cell
    pad = 8
    size = cell + pad * 2
    tmp = pygame.Surface((size, size), pygame.SRCALPHA)
    rect = pygame.Rect(pad, pad, cell, cell)
    draw_arrow_badge(tmp, rect, arrow, highlight=True)
    tmp.set_alpha(int(255 * alpha))

    cx, cy = layout.cell_center(arrow.row, arrow.col)
    surface.blit(tmp, (cx - size // 2 + offset[0], cy - size // 2 + offset[1]))


def draw_text(surface: pygame.Surface, text: str, size: int,
              pos: tuple[int, int], color: tuple[int, int, int] = TEXT_MAIN,
              center: bool = False, bold: bool = False) -> pygame.Rect:
    """绘制一行文字，返回其矩形。"""
    font = load_font(size, bold=bold)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surface.blit(img, rect)
    return rect
