"""pygame 主循环 + 状态机 + 鼠标事件。

状态机：
    "start" | "playing" | "success" | "failed"
"""

from __future__ import annotations

import os

import pygame

from . import view
from .model import Board

# 窗口尺寸
WINDOW_W, WINDOW_H = 900, 700
FPS = 60
TITLE = "一箭又一箭 · Arrow Again Arrow"

STATE_START = "start"
STATE_PLAYING = "playing"
STATE_SUCCESS = "success"
STATE_FAILED = "failed"

# 顶部状态栏区 / 棋盘区 / 底部提示区
HEADER_H = 96
FOOTER_H = 84


class GameApp:
    """承载窗口、绘制与事件分发。

    当前阶段（Step 2）只负责：把棋盘画出来、把箭头画出来、
    处理窗口关闭。点击判定在 Step 4 接入。
    """

    def __init__(self, board: Board | None = None) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = STATE_START

        self.board = board if board is not None else self._demo_board()

        # 棋盘区：去掉上下栏后居中放置
        self.board_area = pygame.Rect(
            40, HEADER_H + 10, WINDOW_W - 80, WINDOW_H - HEADER_H - FOOTER_H - 30
        )
        self.layout = view.BoardLayout(
            self.board.rows, self.board.cols, self.board_area
        )

        self.background = view.vertical_gradient(
            (WINDOW_W, WINDOW_H), view.BG_TOP, view.BG_BOTTOM
        )

        # 被阻挡晃动用的偏移表：{(row, col): 像素偏移}
        self._shake: dict[tuple[int, int], int] = {}
        self._shake_t = 0.0
        self.hover: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # 演示用棋盘（Step 4 换成真实关卡数据）
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

    # ------------------------------------------------------------------
    # 动画辅助
    # ------------------------------------------------------------------
    def trigger_shake(self, r: int, c: int) -> None:
        """让某格箭头晃动（Step 5 由碰撞反馈调用）。"""
        self._shake[(r, c)] = 1
        self._shake_t = 0.0

    def _update_shake(self, dt: float) -> None:
        """按正弦衰减计算晃动偏移。"""
        import math

        self._shake_t += dt
        if self._shake_t > 0.45:
            self._shake.clear()
            return
        # 振幅随时间衰减
        amp = 7.0 * (1 - self._shake_t / 0.45)
        offset = int(math.sin(self._shake_t * 45) * amp)
        for key in list(self._shake):
            self._shake[key] = offset

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.running = False
            return

        if event.type == pygame.MOUSEMOTION:
            self.hover = self.layout.to_cell(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            # 只响应鼠标左键；右键、滚轮等一律忽略
            if event.button != 1:
                return
            cell = self.layout.to_cell(event.pos)
            # Step 4 接入判定；此处先只标记悬停，便于肉眼确认坐标换算正确
            self.hover = cell

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def draw(self) -> None:
        self.screen.blit(self.background, (0, 0))
        self._draw_header()
        view.draw_board(self.screen, self.board, self.layout,
                        shake=self._shake, hover=self.hover)
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
            f"关卡 1/3    剩余箭头 {self.board.remaining()}    "
            f"失误 3/3    用时 00:00"
        )
        view.draw_text(self.screen, info, 20, (40, 62), view.TEXT_DIM)

    def _draw_footer(self) -> None:
        y = WINDOW_H - FOOTER_H + 18
        if self.hover is None:
            hint = "点击箭头所在格子进行判定 · 左键操作 · Esc 退出"
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
            self._update_shake(dt)
            self.draw()
        self.shutdown()
        return 0

    def shutdown(self) -> None:
        view.clear_font_cache()
        pygame.quit()


def run() -> int:
    """无头环境（如 CI）下直接返回，避免调用 set_mode 失败。"""
    if os.environ.get("SDL_VIDEODRIVER", "").lower() == "dummy":
        # 测试环境：不进入主循环
        return 0
    return GameApp().run()
