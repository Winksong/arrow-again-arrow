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
# 碰撞反馈总时长：前段回弹，之后左右晃动
BLOCK_DURATION = 0.50
# 浮动文字存活时长
FLOAT_DURATION = 0.80
# 顶部提示横幅存活时长
BANNER_DURATION = 1.30

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
                     shake_offset: float = 0, highlight: bool = False,
                     recoil: tuple[float, float] = (0.0, 0.0),
                     flash: float = 0.0) -> None:
    """画一个箭头徽章：圆角底板 + 阴影 + 箭头图形。

    shake_offset: 被阻挡时的水平晃动偏移
    recoil:       碰撞回弹偏移 (dx, dy)，沿被挡方向前推后弹回
    flash:        闪红强度 0~1，1 最红
    """
    base_color = DIR_COLORS[arrow.direction]
    color = base_color
    if arrow.state == BLOCKED or flash > 0:
        # 在原本颜色与危险红之间插值。
        # 上限只到 0.75：保留一部分原方向色，避免箭头变成一团红、
        # 让人看不出它原本朝哪边（方向是判定依据，不能丢）。
        t = max(flash * 0.75, 0.55 if arrow.state == BLOCKED else 0.0)
        color = tuple(
            int(base_color[i] + (DANGER[i] - base_color[i]) * t) for i in range(3)
        )

    r = rect.move(int(shake_offset + recoil[0]), int(recoil[1]))
    radius = max(8, r.height // 5)

    # 阴影
    shadow = r.move(0, 3)
    pygame.draw.rect(surface, (14, 16, 22), shadow, border_radius=radius)
    # 底板：被挡时略带红底
    bg = GRID_BG
    if flash > 0 or arrow.state == BLOCKED:
        bg = tuple(int(GRID_BG[i] + (72 - GRID_BG[i]) * 0.55) for i in range(3))
    pygame.draw.rect(surface, bg, r, border_radius=radius)
    # 高光边框
    border = color if (highlight or flash > 0 or arrow.state == BLOCKED) else GRID_LINE
    pygame.draw.rect(surface, border, r, width=2, border_radius=radius)

    draw_arrow_glyph(
        surface,
        (r.centerx, r.centery),
        int(r.height * 0.26),
        arrow.direction,
        color,
    )


def block_recoil(arrow: Arrow, t_sec: float) -> tuple[float, float]:
    """碰撞回弹：沿被挡方向先前推一点再弹回，观感更"撞到了"。

    返回 (dx, dy) 像素偏移。
    """
    p = min(max(t_sec / BLOCK_DURATION, 0.0), 1.0)
    if p >= 1.0:
        return (0.0, 0.0)

    dr, dc = arrow.delta
    # 0~0.18 前推 6px，0.18~0.5 弹回到 0（带一次轻微过冲）
    if p < 0.18:
        k = p / 0.18
        push = 6.0 * k
    elif p < 0.45:
        k = (p - 0.18) / 0.27
        push = 6.0 * (1 - k) - 2.0 * math.sin(k * math.pi)
    else:
        push = 0.0
    return (dc * push, dr * push)


def block_flash(t_sec: float) -> float:
    """闪红强度：快速冲高，随后衰减到 0。"""
    p = min(max(t_sec / BLOCK_DURATION, 0.0), 1.0)
    if p >= 1.0:
        return 0.0
    if p < 0.1:
        return p / 0.1
    return max(1.0 - (p - 0.1) / 0.9, 0.0)


def block_shake(t_sec: float) -> float:
    """晃动偏移：后段左右衰减摆动。"""
    p = min(max(t_sec / BLOCK_DURATION, 0.0), 1.0)
    if p >= 1.0 or p < 0.18:
        return 0.0
    decay = 1.0 - (p - 0.18) / (1.0 - 0.18)
    return math.sin((p - 0.18) * 62) * 7.5 * decay


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
               flying: dict[Arrow, float] | None = None,
               blocking: dict[Arrow, float] | None = None) -> None:
    """绘制棋盘网格与全部箭头。

    shake:    {(row, col): 像素偏移}，被阻挡时的晃动
    flying:   {arrow: 已播放时长}，飞出动画（平移 + 淡出 + 残影）
    blocking: {arrow: 已播放时长}，碰撞反馈（回弹 + 闪红 + 晃动）
    """
    shake = shake or {}
    flying = flying or {}
    blocking = blocking or {}

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
        t = blocking.get(arrow)
        if t is not None:
            recoil = block_recoil(arrow, t)
            flash = block_flash(t)
            shake_off = block_shake(t)
        else:
            recoil = (0.0, 0.0)
            flash = 0.0
            shake_off = shake.get((arrow.row, arrow.col), 0.0)

        draw_arrow_badge(
            surface, rect, arrow,
            shake_offset=shake_off,
            highlight=hover == (arrow.row, arrow.col),
            recoil=recoil,
            flash=flash,
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


# --------------------------------------------------------------------------
# Step 5：失误次数可视化
# --------------------------------------------------------------------------

def draw_mistake_hearts(surface: pygame.Surface, pos: tuple[int, int],
                        left: int, total: int, pulse: float = 0.0) -> pygame.Rect:
    """用「心/盾」图标显示剩余失误次数。

    剩余为图标亮色，已消耗为空心暗色；pulse 为刚扣失误时的闪动强度。
    返回整体矩形，便于布局。
    """
    size = 22
    gap = 8
    x, y = pos
    r = size // 2

    for i in range(total):
        cx = x + i * (size + gap) + r
        cy = y + r
        alive = i < left
        if alive:
            color = OK_COLOR if left > 1 else (255, 183, 77)
            if pulse > 0:
                color = tuple(
                    int(color[j] + (DANGER[j] - color[j]) * pulse) for j in range(3)
                )
            pygame.draw.circle(surface, color, (cx, cy), r)
            pygame.draw.circle(surface, (255, 255, 255), (cx - 3, cy - 4), 2)
        else:
            pygame.draw.circle(surface, (56, 62, 78), (cx, cy), r)
            pygame.draw.circle(surface, (78, 86, 106), (cx, cy), r, width=2)

    w = total * size + (total - 1) * gap
    return pygame.Rect(x, y, w, size)


# --------------------------------------------------------------------------
# Step 5：浮动文字（+/- 提示）
# --------------------------------------------------------------------------

def draw_float_text(surface: pygame.Surface, text: str,
                    center: tuple[int, int], t_sec: float,
                    color: tuple[int, int, int]) -> None:
    """在棋盘上方绘制向上飘并淡出的文字。

    t_sec 为已存活时长；超过 FLOAT_DURATION 不再绘制。
    """
    if t_sec >= FLOAT_DURATION:
        return
    p = t_sec / FLOAT_DURATION
    rise = -34 * (p ** 0.7)                 # 逐渐上飘
    alpha = 1.0 if p < 0.55 else max(1.0 - (p - 0.55) / 0.45, 0.0)

    font = load_font(24, bold=True)
    img = font.render(text, True, color)
    img.set_alpha(int(255 * alpha))

    # 描边：画一圈深色底衬，保证在任何背景上都看得清
    outline = font.render(text, True, (16, 18, 24))
    outline.set_alpha(int(200 * alpha))
    x = center[0] - img.get_width() // 2
    # 起点抬到格子上方，避免与箭头本体重叠
    y = int(center[1] - 34 + rise)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        surface.blit(outline, (x + dx, y + dy))
    surface.blit(img, (x, y))


def float_scale(t_sec: float) -> float:
    """浮动文字的弹出缩放：先放大超过 1，再回落到 1。"""
    p = min(t_sec / 0.18, 1.0)
    if p >= 1.0:
        return 1.0
    return 0.6 + 0.55 * p - 0.15 * (p ** 2) * 1.0


# --------------------------------------------------------------------------
# Step 5：碰撞提示条
# --------------------------------------------------------------------------

def draw_banner(surface: pygame.Surface, rect: pygame.Rect, text: str,
                color: tuple[int, int, int], alpha: float = 1.0) -> None:
    """在指定区域绘制一条不透明提示横幅（用于「被挡住了」等反馈）。"""
    if alpha <= 0.02:
        return
    tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(tmp, (*color, int(56 * alpha)), tmp.get_rect(),
                     border_radius=10)
    pygame.draw.rect(tmp, (*color, int(200 * alpha)), tmp.get_rect(),
                     width=2, border_radius=10)
    surface.blit(tmp, rect.topleft)

    font = load_font(20, bold=True)
    img = font.render(text, True, color)
    img.set_alpha(int(255 * alpha))
    surface.blit(img, (rect.x + 14, rect.centery - img.get_height() // 2))


# --------------------------------------------------------------------------
# 结果卡片（Step 7）
# --------------------------------------------------------------------------
# ⚠️ 关键约定：结果卡片必须用 **不透明底 + 卡片内相对定位**。
# 早期用「半透明遮罩 + 居中文字」的写法，会让文字与背后的棋盘重叠、
# 压住按钮，观感很差。所有元素坐标一律相对卡片 rect 计算。


class Button:
    """一个可点击的按钮（矩形 + 文案 + 配色），坐标相对卡片。"""

    def __init__(self, rect: pygame.Rect, text: str,
                 color: tuple[int, int, int] = OK_COLOR) -> None:
        self.rect = rect
        self.text = text
        self.color = color

    def hit(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def draw(self, surface: pygame.Surface,
             hovered: bool = False) -> None:
        bg = tuple(min(c + 28, 255) for c in self.color) if hovered \
            else self.color
        pygame.draw.rect(surface, (14, 16, 22), self.rect.move(0, 3),
                         border_radius=10)
        pygame.draw.rect(surface, bg, self.rect, border_radius=10)
        if hovered:
            pygame.draw.rect(surface, (255, 255, 255), self.rect,
                             width=2, border_radius=10)

        font = load_font(22, bold=True)
        img = font.render(self.text, True, (18, 20, 28))
        surface.blit(img, img.get_rect(center=self.rect.center))


def draw_result_card(surface: pygame.Surface, area: pygame.Rect, title: str,
                     subtitle: str, lines: list[str],
                     buttons: list[Button], title_color: tuple[int, int, int],
                     hovered: Button | None = None,
                     dim_background: bool = True) -> None:
    """绘制结果卡片（通关 / 失败共用）。

    area:    卡片区域（屏幕坐标）
    buttons: 按钮列表，坐标必须**相对卡片** —— 本函数会做偏移
    """
    if dim_background:
        # 压暗背景，但卡片本身是不透明的，文字不会与棋盘重叠
        veil = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        veil.fill((10, 12, 18, 170))
        surface.blit(veil, (0, 0))

    card = area
    # 阴影 + 卡片主体（完全不透明）
    pygame.draw.rect(surface, (12, 14, 20), card.move(0, 6), border_radius=20)
    pygame.draw.rect(surface, CARD_BG, card, border_radius=20)
    pygame.draw.rect(surface, title_color, card, width=3, border_radius=20)

    # ---- 卡片内所有元素相对 card 定位 ----
    title_img = load_font(42, bold=True).render(title, True, title_color)
    surface.blit(title_img, title_img.get_rect(
        center=(card.centerx, card.y + 74)))

    sub_img = load_font(22).render(subtitle, True, TEXT_DIM)
    surface.blit(sub_img, sub_img.get_rect(
        center=(card.centerx, card.y + 122)))

    # 分隔线
    pygame.draw.line(surface, (72, 82, 106),
                     (card.x + 40, card.y + 152),
                     (card.right - 40, card.y + 152), 2)

    y = card.y + 182
    for line in lines:
        img = load_font(20).render(line, True, TEXT_MAIN)
        surface.blit(img, img.get_rect(center=(card.centerx, y)))
        y += 32

    for btn in buttons:
        btn.draw(surface, hovered=btn is hovered)


def card_layout(screen_size: tuple[int, int], width: int = 460,
                height: int = 380) -> pygame.Rect:
    """结果卡片在屏幕中央的矩形。"""
    w, h = screen_size
    return pygame.Rect((w - width) // 2, (h - height) // 2, width, height)


def make_buttons(card: pygame.Rect, specs: list[tuple[str, str]],
                 y: int | None = None) -> list[Button]:
    """根据卡片位置生成一排按钮。

    specs: [(文案, 类型), ...]，类型取 "ok" / "warn" / "dim"
    返回的按钮 rect 已是屏幕坐标（相对卡片算好后加上偏移）。
    """
    colors = {"ok": OK_COLOR, "warn": (255, 183, 77), "dim": (120, 132, 158)}
    if y is None:
        y = card.bottom - 92

    n = len(specs)
    btn_w, btn_h, gap = 170, 52, 20
    total_w = n * btn_w + (n - 1) * gap
    x = card.centerx - total_w // 2

    buttons: list[Button] = []
    for text, kind in specs:
        rect = pygame.Rect(x, y, btn_w, btn_h)
        buttons.append(Button(rect, text, colors.get(kind, OK_COLOR)))
        x += btn_w + gap
    return buttons
