"""pygame 主循环 + 状态机 + 鼠标事件。

状态机：
    "start" | "playing" | "success" | "failed"
"""

from __future__ import annotations

import os

import pygame

from . import view
from .model import (
    BLOCKED,
    FLYING,
    IDLE,
    STATE_FAILED,
    STATE_PLAYING,
    STATE_SUCCESS,
    Arrow,
    Board,
    Session,
)

# 窗口尺寸
WINDOW_W, WINDOW_H = 900, 700
FPS = 60
TITLE = "一箭又一箭 · Arrow Again Arrow"

STATE_START = "start"

# 顶部状态栏区 / 棋盘区 / 底部提示区
HEADER_H = 104
FOOTER_H = 84

# 动画时长（秒）—— 定义在 view 层，供绘制与逻辑共用，避免两处不一致
FLY_DURATION = view.FLY_DURATION
BLOCK_DURATION = view.BLOCK_DURATION
FLOAT_DURATION = view.FLOAT_DURATION
BANNER_DURATION = view.BANNER_DURATION


class FloatText:
    """一条向上飘并淡出的浮动文字。"""

    __slots__ = ("text", "center", "color", "t")

    def __init__(self, text: str, center: tuple[int, int],
                 color: tuple[int, int, int]) -> None:
        self.text = text
        self.center = center
        self.color = color
        self.t = 0.0

    @property
    def alive(self) -> bool:
        return self.t < FLOAT_DURATION


class GameApp:
    """承载窗口、绘制与事件分发。

    逻辑判定全部委托给 Session；本类只负责
    「输入 → Session → 动画 → 绘制」这条链路。
    """

    def __init__(self, session: Session | None = None) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = STATE_START

        self.session = session if session is not None else Session(
            board=self._demo_board(), mistakes_left=3
        )
        self.board = self.session.board
        self.initial_mistakes = self.session.mistakes_left

        # 棋盘区：去掉上下栏后居中放置
        self.board_area = pygame.Rect(
            40, HEADER_H + 10, WINDOW_W - 80, WINDOW_H - HEADER_H - FOOTER_H - 30
        )
        self._rebuild_layout()

        self.background = view.vertical_gradient(
            (WINDOW_W, WINDOW_H), view.BG_TOP, view.BG_BOTTOM
        )

        # --- 动画状态 ---
        # 正在飞出的箭头：arrow → 已播放时长
        self._flying: dict[Arrow, float] = {}
        # 正在做碰撞反馈的箭头：arrow → 已播放时长
        self._blocking: dict[Arrow, float] = {}
        # 浮动文字列表
        self._floats: list[FloatText] = []
        # 顶部提示横幅：(文字, 颜色, 已存活时长)
        self._banner: tuple[str, tuple[int, int, int], float] | None = None
        # 失误心跳动
        self._mistake_pulse = 0.0

        self.hover: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # 演示用棋盘（Step 6 换成真实关卡数据）
    # ------------------------------------------------------------------
    @staticmethod
    def _demo_board() -> Board:
        return Board.from_spec(4, 5, [
            # (row, col, direction)
            (0, 0, "right"), (0, 3, "down"),
            (1, 2, "left"), (1, 4, "up"),
            (2, 1, "down"), (2, 4, "left"),
            (3, 0, "up"), (3, 3, "right"),
        ])

    def _rebuild_layout(self) -> None:
        self.layout = view.BoardLayout(
            self.board.rows, self.board.cols, self.board_area
        )

    # ------------------------------------------------------------------
    # 动画状态
    # ------------------------------------------------------------------
    @property
    def animating(self) -> bool:
        """是否有动画在播 —— 期间忽略点击，防止连点刷失误。"""
        return bool(self._flying) or bool(self._blocking)

    def _start_collision_feedback(self, arrow: Arrow) -> None:
        """启动一次碰撞反馈：回弹 + 闪红 + 晃动。"""
        self._blocking[arrow] = 0.0

    def _update_animations(self, dt: float) -> None:
        self._update_flying(dt)
        self._update_blocking(dt)
        self._update_floats(dt)
        self._update_banner(dt)

    def _update_flying(self, dt: float) -> None:
        """推进飞出动画；播完则通知 Session 移除箭头。"""
        finished: list[Arrow] = []
        for arrow, t in list(self._flying.items()):
            t += dt
            arrow.anim_t = min(t / FLY_DURATION, 1.0)
            if t >= FLY_DURATION:
                finished.append(arrow)
            else:
                self._flying[arrow] = t

        for arrow in finished:
            self._flying.pop(arrow, None)
            self.session.on_fly_finished(arrow)

    def _update_blocking(self, dt: float) -> None:
        """推进碰撞反馈；播完把 blocked 标记清回 idle。"""
        done: list[Arrow] = []
        for arrow, t in list(self._blocking.items()):
            t += dt
            if t >= BLOCK_DURATION:
                done.append(arrow)
            else:
                self._blocking[arrow] = t

        for arrow in done:
            self._blocking.pop(arrow, None)
            if arrow.state == BLOCKED:
                arrow.state = IDLE

    def _update_floats(self, dt: float) -> None:
        for f in self._floats:
            f.t += dt
        self._floats = [f for f in self._floats if f.alive]

    def _update_banner(self, dt: float) -> None:
        if self._banner is None:
            return
        text, color, t = self._banner
        t += dt
        self._banner = None if t >= BANNER_DURATION else (text, color, t)

        if self._mistake_pulse > 0:
            self._mistake_pulse = max(self._mistake_pulse - dt / 0.45, 0.0)

    def _add_float(self, text: str, cell: tuple[int, int],
                   color: tuple[int, int, int]) -> None:
        self._floats.append(FloatText(text, self.layout.cell_center(*cell), color))

    def _set_banner(self, text: str, color: tuple[int, int, int]) -> None:
        self._banner = (text, color, 0.0)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_r and self.state != STATE_START:
                self.restart()
            return

        if event.type == pygame.MOUSEMOTION:
            self.hover = self.layout.to_cell(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            # 只响应鼠标左键；右键、滚轮、长按一律忽略
            if event.button != 1:
                return
            if self.state == STATE_START:
                self.state = STATE_PLAYING
                return
            self.on_click(event.pos)

    def on_click(self, pos: tuple[int, int]) -> str:
        """把屏幕坐标交给 Session 判定，并驱动相应动画与反馈。"""
        cell = self.layout.to_cell(pos)
        if cell is None:
            return "empty"

        # 动画期间忽略点击（重开、关窗不受影响，走键盘/窗口事件）
        if self.animating:
            return "busy"

        r, c = cell

        # 先取「点击前的目标箭头」：一旦 click 把它置为 flying，
        # arrow_at() 就会返回 None（flying 不参与判定），所以必须提前拿。
        target = self.board.arrow_at(r, c)

        result = self.session.click(r, c)

        if result == "fly":
            if target is not None and target.state == FLYING:
                self._flying[target] = 0.0

        elif result == "blocked":
            if target is not None:
                self._start_collision_feedback(target)
                self._add_float("失误 -1", (r, c), view.DANGER)
            self._mistake_pulse = 1.0
            # 指出被谁挡住了，帮玩家理解规则
            blocker = self.board.blocking_arrow(target) if target else None
            if blocker is not None:
                self._set_banner(
                    f"被 ({blocker.row}, {blocker.col}) 挡住了！失误 -1", view.DANGER
                )
            else:
                self._set_banner("被挡住了！失误 -1", view.DANGER)

        return result

    def restart(self) -> None:
        """重开本关：布局、失误、动画状态全部恢复初始值。"""
        self._flying.clear()
        self._blocking.clear()
        self._floats.clear()
        self._banner = None
        self._mistake_pulse = 0.0
        self.hover = None

        layout = self.board.snapshot()
        rows, cols = self.board.rows, self.board.cols
        self.session = Session(
            board=Board.from_spec(rows, cols, layout),
            mistakes_left=self.initial_mistakes,
        )
        self.board = self.session.board
        self._rebuild_layout()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def draw(self) -> None:
        self.screen.blit(self.background, (0, 0))
        self._draw_header()
        view.draw_board(
            self.screen, self.board, self.layout,
            hover=self.hover, flying=self._flying, blocking=self._blocking,
        )
        self._draw_floats()
        self._draw_footer()
        pygame.display.flip()

    def _draw_header(self) -> None:
        bar = pygame.Rect(0, 0, WINDOW_W, HEADER_H)
        pygame.draw.rect(self.screen, (24, 28, 38), bar)
        pygame.draw.line(self.screen, view.GRID_LINE,
                         (0, HEADER_H - 1), (WINDOW_W, HEADER_H - 1), 2)

        view.draw_text(self.screen, "一箭又一箭", 28,
                       (40, 18), view.TEXT_MAIN, bold=True)

        # 剩余箭头
        view.draw_text(self.screen, f"剩余箭头 {self.board.remaining()}", 19,
                       (40, 62), view.TEXT_DIM)

        # 失误次数：图标式显示
        left = self.session.mistakes_left
        total = max(self.initial_mistakes, 1)
        view.draw_text(self.screen, "失误", 19, (232, 62), view.TEXT_DIM)
        hearts_x = 292
        view.draw_mistake_hearts(
            self.screen, (hearts_x, 60), left, total, pulse=self._mistake_pulse
        )
        heart_w = total * 22 + (total - 1) * 8
        view.draw_text(self.screen, f"{left}/{total}", 19,
                       (hearts_x + heart_w + 14, 62), view.TEXT_DIM)

        # 提示横幅
        if self._banner is not None:
            text, color, t = self._banner
            alpha = 1.0 if t < BANNER_DURATION - 0.35 else \
                max((BANNER_DURATION - t) / 0.35, 0.0)
            rect = pygame.Rect(WINDOW_W - 400, 26, 360, 42)
            view.draw_banner(self.screen, rect, text, color, alpha)

    def _draw_floats(self) -> None:
        for f in self._floats:
            view.draw_float_text(self.screen, f.text, f.center, f.t, f.color)

    def _draw_footer(self) -> None:
        y = WINDOW_H - FOOTER_H + 18
        if self.animating:
            hint = "反馈播放中……"
            color = view.TEXT_DIM
        elif self.hover is None:
            hint = "点击箭头所在格子进行判定 · 左键操作 · R 重开 · Esc 退出"
            color = view.TEXT_DIM
        else:
            r, c = self.hover
            a = self.board.arrow_at(r, c)
            if a is None:
                hint = f"格子 ({r}, {c}) 为空"
                color = view.TEXT_DIM
            else:
                blocked = self.board.blocking_arrow(a)
                if blocked is None:
                    hint = f"格子 ({r}, {c}) 前方无阻挡 → 点击可飞出"
                    color = view.OK_COLOR
                else:
                    hint = (f"格子 ({r}, {c}) 被 ({blocked.row}, {blocked.col}) "
                            f"阻挡 → 点击会扣失误")
                    color = view.DANGER
        view.draw_text(self.screen, hint, 19, (40, y), color)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self) -> int:
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                self.handle_event(event)
            self._update_animations(dt)
            self.draw()
        self.shutdown()
        return 0

    def shutdown(self) -> None:
        view.clear_font_cache()
        pygame.quit()


def run() -> int:
    """无头环境（如 CI）下直接返回，避免调用 set_mode 失败。"""
    if os.environ.get("SDL_VIDEODRIVER", "").lower() == "dummy":
        return 0
    return GameApp().run()
