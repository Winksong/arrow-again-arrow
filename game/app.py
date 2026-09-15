"""pygame 主循环 + 状态机 + 鼠标事件。

状态机：
    "start" | "playing" | "success" | "failed"
"""

from __future__ import annotations

import math
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
HEADER_H = 96
FOOTER_H = 84

# 动画时长（秒）—— 定义在 view 层，供绘制与逻辑共用，避免两处不一致
FLY_DURATION = view.FLY_DURATION
SHAKE_DURATION = view.SHAKE_DURATION


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

        # 被阻挡晃动用的偏移表：{(row, col): 像素偏移}
        self._shake: dict[tuple[int, int], float] = {}
        self._shake_t = 0.0

        # 正在飞出的箭头：arrow → 已播放时长
        self._flying: dict[Arrow, float] = {}

        self.hover: tuple[int, int] | None = None
        self.toast: tuple[str, tuple[int, int, int], float] | None = None

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
    # 动画辅助
    # ------------------------------------------------------------------
    @property
    def animating(self) -> bool:
        """是否有动画在播 —— 期间忽略点击，防止连点刷失误。"""
        return bool(self._flying) or bool(self._shake)

    def _start_shake(self, r: int, c: int) -> None:
        self._shake[(r, c)] = 0.0
        self._shake_t = 0.0

    def _update_animations(self, dt: float) -> None:
        self._update_flying(dt)
        self._update_shake(dt)

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

    def _update_shake(self, dt: float) -> None:
        """按正弦衰减计算晃动偏移。"""
        if not self._shake:
            return
        self._shake_t += dt
        if self._shake_t > SHAKE_DURATION:
            self._shake.clear()
            return
        amp = 8.0 * (1 - self._shake_t / SHAKE_DURATION)
        offset = math.sin(self._shake_t * 46) * amp
        for key in self._shake:
            self._shake[key] = offset

    def _expire_blocked(self) -> None:
        """晃动结束后把 blocked 标记清回 idle，避免箭头一直红着。"""
        for a in self.board.arrows:
            if a.state == BLOCKED and (a.row, a.col) not in self._shake:
                a.state = IDLE

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
            elif event.key == pygame.K_r:
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
        """把屏幕坐标交给 Session 判定，并驱动相应动画。"""
        cell = self.layout.to_cell(pos)
        if cell is None:
            return "empty"

        # 动画期间忽略点击（重开、关窗不受影响，走键盘/窗口事件）
        if self.animating:
            return "busy"

        r, c = cell

        # 先取「点击前的目标箭头」，一旦 click 把它置为 flying，
        # arrow_at() 就会返回 None（flying 不参与判定），所以必须提前拿。
        target = self.board.arrow_at(r, c)

        result = self.session.click(r, c)

        if result == "fly":
            # 这里用预取的 target，不能再调 arrow_at
            if target is not None and target.state == FLYING:
                self._flying[target] = 0.0
        elif result == "blocked":
            self._start_shake(r, c)
            self._set_toast("被挡住了！失误 -1", view.DANGER)
        return result

    def _set_toast(self, text: str, color: tuple[int, int, int]) -> None:
        self.toast = (text, color, 0.0)

    def restart(self) -> None:
        """重开本关：布局、失误、动画状态全部恢复初始值。"""
        self._flying.clear()
        self._shake.clear()
        self._shake_t = 0.0
        self.toast = None
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
            shake=self._shake, hover=self.hover, flying=self._flying,
        )
        self._draw_footer()
        pygame.display.flip()

    def _draw_header(self) -> None:
        bar = pygame.Rect(0, 0, WINDOW_W, HEADER_H)
        pygame.draw.rect(self.screen, (24, 28, 38), bar)
        pygame.draw.line(self.screen, view.GRID_LINE,
                         (0, HEADER_H - 1), (WINDOW_W, HEADER_H - 1), 2)

        view.draw_text(self.screen, "一箭又一箭", 30,
                       (40, 22), view.TEXT_MAIN, bold=True)

        info = (
            f"剩余箭头 {self.board.remaining()}    "
            f"失误 {self.session.mistakes_left}/3"
        )
        view.draw_text(self.screen, info, 20, (40, 62), view.TEXT_DIM)

        # 右上角浮动提示（右对齐）
        if self.toast is not None:
            text, color, t = self.toast
            img = view.load_font(20).render(text, True, color)
            # 最后 0.3s 淡出
            remain = 1.1 - t
            if remain < 0.3:
                img.set_alpha(max(int(255 * remain / 0.3), 0))
            self.screen.blit(img, (WINDOW_W - 40 - img.get_width(), 30))

    def _draw_footer(self) -> None:
        y = WINDOW_H - FOOTER_H + 18
        if self.hover is None:
            hint = "点击箭头所在格子进行判定 · 左键操作 · R 重开 · Esc 退出"
            color = view.TEXT_DIM
        else:
            r, c = self.hover
            a = self.board.arrow_at(r, c)
            if a is None:
                if self.animating:
                    hint = "动画播放中……"
                else:
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
            self._expire_blocked()
            if self.toast is not None:
                text, color, t = self.toast
                t += dt
                if t > 1.1:
                    self.toast = None
                else:
                    self.toast = (text, color, t)
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
