"""pygame 主循环 + 状态机 + 鼠标事件。

状态机：
    "start" | "playing" | "success" | "failed" | "allclear"
"""

from __future__ import annotations

import os

import pygame

from . import levels as levels_mod
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

# 游戏状态
STATE_START = "start"
STATE_ALLCLEAR = "allclear"

# 区域划分
HEADER_H = 104
FOOTER_H = 84

# 动画时长（秒）—— 定义在 view 层，供绘制与逻辑共用
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

    逻辑判定全部委托给 Session；结果界面由状态机驱动。
    """

    def __init__(self, session: Session | None = None,
                 level_index: int = 0) -> None:
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = STATE_START
        self.level_index = max(0, min(level_index, levels_mod.level_count() - 1))

        self.board_area = pygame.Rect(
            40, HEADER_H + 10, WINDOW_W - 80, WINDOW_H - HEADER_H - FOOTER_H - 30
        )
        self.background = view.vertical_gradient(
            (WINDOW_W, WINDOW_H), view.BG_TOP, view.BG_BOTTOM
        )

        self._flying: dict[Arrow, float] = {}
        self._blocking: dict[Arrow, float] = {}
        self._floats: list[FloatText] = []
        self._banner: tuple[str, tuple[int, int, int], float] | None = None
        self._mistake_pulse = 0.0
        self.hover: tuple[int, int] | None = None
        self._hover_button: view.Button | None = None

        if session is not None:
            # 测试注入：以传入的 Session 为准，并记住它的初始布局，
            # 使 restart() 恢复到「注入时的布局」而不是关卡数据。
            self.session = session
            self.level = {"name": "自定义关卡",
                          "rows": session.board.rows,
                          "cols": session.board.cols,
                          "mistakes": session.mistakes_left}
            self.initial_mistakes = session.mistakes_left
            self._injected_layout = list(
                (a.row, a.col, a.direction) for a in session.board.active_arrows
            )
        else:
            self.session, self.level = self._build_session(self.level_index)
            self.initial_mistakes = self.level["mistakes"]
            self._injected_layout = None

        self.board = self.session.board
        self._rebuild_layout()

    # ------------------------------------------------------------------
    # 关卡装载
    # ------------------------------------------------------------------
    @staticmethod
    def _build_session(index: int) -> tuple[Session, dict]:
        """按索引构造一关的 Session。"""
        lv = levels_mod.get_level(index)
        arrows = levels_mod.level_arrows(lv)
        board = Board.from_spec(lv["rows"], lv["cols"], arrows)
        session = Session(board=board, mistakes_left=lv["mistakes"])
        return session, lv

    def load_level(self, index: int) -> None:
        """装载指定关卡，并清空全部动画与反馈状态。"""
        self.level_index = max(0, min(index, levels_mod.level_count() - 1))
        self.session, self.level = self._build_session(self.level_index)
        self.board = self.session.board
        self.initial_mistakes = self.level["mistakes"]
        self._reset_transient()
        self.state = STATE_PLAYING

    def restart(self) -> None:
        """重开本关：布局、失误、动画状态全部恢复初始值。

        若 App 是用注入的 Session 构造的（测试场景），则恢复到注入时的布局；
        否则重新装载当前关卡数据。
        """
        if self._injected_layout is not None:
            self.session = Session(
                board=Board.from_spec(
                    self.level["rows"], self.level["cols"], self._injected_layout
                ),
                mistakes_left=self.initial_mistakes,
            )
            self.board = self.session.board
            self._reset_transient()
            self.state = STATE_PLAYING
            return
        self.load_level(self.level_index)

    def next_level(self) -> None:
        """进入下一关；已是最后一关则进入全通关界面。"""
        if self.level_index + 1 >= levels_mod.level_count():
            self._reset_transient()
            self.state = STATE_ALLCLEAR
            return
        self.load_level(self.level_index + 1)

    def back_to_start(self) -> None:
        self._reset_transient()
        self.state = STATE_START

    def _reset_transient(self) -> None:
        self._flying.clear()
        self._blocking.clear()
        self._floats.clear()
        self._banner = None
        self._mistake_pulse = 0.0
        self.hover = None
        self._hover_button = None
        self._rebuild_layout()

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

    @property
    def in_result_screen(self) -> bool:
        """是否处于结果界面（此状态下底层棋盘不响应点击）。"""
        return self.state in (STATE_SUCCESS, STATE_FAILED, STATE_ALLCLEAR,
                              STATE_START)

    def _start_collision_feedback(self, arrow: Arrow) -> None:
        self._blocking[arrow] = 0.0

    def _update_animations(self, dt: float) -> None:
        self._update_flying(dt)
        self._update_blocking(dt)
        self._update_floats(dt)
        self._update_banner(dt)
        self._sync_result_state()

    def _sync_result_state(self) -> None:
        """把 Session 的胜负结果同步到界面状态机。

        必须在所有动画播完之后再同步，避免"动画还没播完就弹结果卡片"。
        失误耗尽走的是碰撞反馈（不是飞出动画），所以这里统一判断。
        """
        if self.state != STATE_PLAYING:
            return
        if self.animating:
            return
        if self.session.state == STATE_SUCCESS:
            self.state = STATE_SUCCESS
        elif self.session.state == STATE_FAILED:
            self.state = STATE_FAILED

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
        if self._mistake_pulse > 0:
            self._mistake_pulse = max(self._mistake_pulse - dt / 0.45, 0.0)
        if self._banner is None:
            return
        text, color, t = self._banner
        t += dt
        self._banner = None if t >= BANNER_DURATION else (text, color, t)

    def _add_float(self, text: str, cell: tuple[int, int],
                   color: tuple[int, int, int]) -> None:
        self._floats.append(FloatText(text, self.layout.cell_center(*cell), color))

    def _set_banner(self, text: str, color: tuple[int, int, int]) -> None:
        self._banner = (text, color, 0.0)

    # ------------------------------------------------------------------
    # 结果界面的按钮
    # ------------------------------------------------------------------
    def result_buttons(self) -> list[view.Button]:
        """按当前状态返回结果界面的按钮列表。"""
        card = view.card_layout((WINDOW_W, WINDOW_H))
        if self.state == STATE_SUCCESS:
            specs = [("下一关", "ok"), ("重开本关", "dim")]
        elif self.state == STATE_FAILED:
            specs = [("重开本关", "warn"), ("返回开始", "dim")]
        elif self.state == STATE_ALLCLEAR:
            specs = [("返回开始", "ok")]
        elif self.state == STATE_START:
            specs = [("开始游戏", "ok")]
        else:
            return []
        return view.make_buttons(card, specs)

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
            elif event.key == pygame.K_r and not self.in_result_screen:
                self.restart()
            elif event.key == pygame.K_SPACE and self.state == STATE_START:
                self.load_level(0)
            return

        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN:
            # 只响应鼠标左键；右键、滚轮、长按一律忽略
            if event.button != 1:
                return
            self.on_click(event.pos)

    def _update_hover(self, pos: tuple[int, int]) -> None:
        self._hover_button = None
        if self.in_result_screen:
            for btn in self.result_buttons():
                if btn.hit(pos):
                    self._hover_button = btn
                    break
            self.hover = None
        else:
            self.hover = self.layout.to_cell(pos)

    def on_click(self, pos: tuple[int, int]) -> str:
        """统一入口：结果界面走按钮，游戏界面走棋盘判定。"""
        if self.state == STATE_START:
            for btn in self.result_buttons():
                if btn.hit(pos):
                    self.load_level(0)
                    return "start"
            return "ignored"

        if self.state in (STATE_SUCCESS, STATE_FAILED, STATE_ALLCLEAR):
            return self._on_result_click(pos)

        return self._on_board_click(pos)

    def _on_result_click(self, pos: tuple[int, int]) -> str:
        for btn in self.result_buttons():
            if not btn.hit(pos):
                continue
            if btn.text == "下一关":
                self.next_level()
                return "next_level"
            if btn.text == "重开本关":
                self.restart()
                return "restart"
            if btn.text == "返回开始":
                self.back_to_start()
                return "back"
        return "ignored"

    def _on_board_click(self, pos: tuple[int, int]) -> str:
        """棋盘判定：屏幕坐标 → 格子 → Session。"""
        cell = self.layout.to_cell(pos)
        if cell is None:
            return "empty"

        # 动画期间忽略点击（重开、关窗不受影响）
        if self.animating:
            return "busy"

        r, c = cell
        # 先取点击前的目标箭头：click 会把它置为 flying，
        # 之后 arrow_at() 就返回 None 了。
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
            blocker = self.board.blocking_arrow(target) if target else None
            if blocker is not None:
                self._set_banner(
                    f"被 ({blocker.row}, {blocker.col}) 挡住了！失误 -1", view.DANGER
                )
            else:
                self._set_banner("被挡住了！失误 -1", view.DANGER)

        return result

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def draw(self) -> None:
        self.screen.blit(self.background, (0, 0))

        if self.state == STATE_START:
            self._draw_start_screen()
        else:
            self._draw_header()
            view.draw_board(
                self.screen, self.board, self.layout,
                hover=self.hover, flying=self._flying, blocking=self._blocking,
            )
            self._draw_floats()
            self._draw_footer()
            self._draw_result_if_needed()

        pygame.display.flip()

    def _draw_start_screen(self) -> None:
        card = view.card_layout((WINDOW_W, WINDOW_H), width=560, height=400)
        view.draw_text(self.screen, "一箭又一箭", 52,
                       (WINDOW_W // 2, card.y + 92), view.TEXT_MAIN,
                       center=True, bold=True)
        view.draw_text(self.screen, "点击箭头，让它沿方向飞出棋盘", 22,
                       (WINDOW_W // 2, card.y + 152), view.TEXT_DIM, center=True)

        rules = [
            "前方无阻挡 → 箭头飞出并消失",
            "前方有阻挡 → 留在原地，失误 -1",
            "只判定同一行或同一列，阻挡箭头的朝向不计",
            "清空全部箭头即可通关",
        ]
        y = card.y + 198
        for line in rules:
            view.draw_text(self.screen, line, 19,
                           (WINDOW_W // 2, y), view.TEXT_DIM, center=True)
            y += 30

        for btn in self.result_buttons():
            btn.draw(self.screen, hovered=btn is self._hover_button)

    def _draw_header(self) -> None:
        bar = pygame.Rect(0, 0, WINDOW_W, HEADER_H)
        pygame.draw.rect(self.screen, (24, 28, 38), bar)
        pygame.draw.line(self.screen, view.GRID_LINE,
                         (0, HEADER_H - 1), (WINDOW_W, HEADER_H - 1), 2)

        view.draw_text(self.screen, self.level["name"], 26,
                       (40, 18), view.TEXT_MAIN, bold=True)

        # 状态栏第二行用固定列位布局，避免各项文字互相挤压
        total_levels = levels_mod.level_count()
        col1_x = 40
        view.draw_text(
            self.screen,
            f"关卡 {self.level_index + 1}/{total_levels}", 19, (col1_x, 62),
            view.TEXT_DIM,
        )

        col2_x = col1_x + 128
        view.draw_text(
            self.screen,
            f"剩余箭头 {self.board.remaining()}", 19, (col2_x, 62),
            view.TEXT_DIM,
        )

        # 失误次数：图标式显示
        left = self.session.mistakes_left
        total = max(self.initial_mistakes, 1)
        col3_x = col2_x + 150
        view.draw_text(self.screen, "失误", 19, (col3_x, 62), view.TEXT_DIM)

        hearts_x = col3_x + 52
        view.draw_mistake_hearts(
            self.screen, (hearts_x, 60), left, total, pulse=self._mistake_pulse
        )
        heart_w = total * 22 + (total - 1) * 8
        view.draw_text(self.screen, f"{left}/{total}", 19,
                       (hearts_x + heart_w + 12, 62), view.TEXT_DIM)

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
        if self.in_result_screen:
            hint = "点击按钮继续 · Esc 退出"
            color = view.TEXT_DIM
        elif self.animating:
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

    def _draw_result_if_needed(self) -> None:
        """绘制结果卡片。使用不透明底 + 卡片内相对定位，避免文字与棋盘重叠。"""
        if self.state not in (STATE_SUCCESS, STATE_FAILED, STATE_ALLCLEAR):
            return

        card = view.card_layout((WINDOW_W, WINDOW_H))
        total_levels = levels_mod.level_count()

        if self.state == STATE_SUCCESS:
            remaining = self.session.mistakes_left
            lines = [
                f"用掉失误：{self.initial_mistakes - remaining} / {self.initial_mistakes}",
                f"本关箭头：{self.session.arrows_total} 个",
            ]
            subtitle = f"本关完成 · 共 {total_levels} 关"
            view.draw_result_card(
                self.screen, card, "通关！", subtitle, lines,
                self.result_buttons(), view.OK_COLOR,
                hovered=self._hover_button,
            )

        elif self.state == STATE_FAILED:
            cleared = self.session.arrows_total - self.board.remaining()
            lines = [
                f"已消除：{cleared} / {self.session.arrows_total} 个箭头",
                "失误次数已用尽",
            ]
            view.draw_result_card(
                self.screen, card, "本关失败", "别灰心，再试一次",
                lines, self.result_buttons(), view.DANGER,
                hovered=self._hover_button,
            )

        else:  # STATE_ALLCLEAR
            view.draw_result_card(
                self.screen, card, "全部通关！",
                f"你完成了全部 {total_levels} 关",
                ["感谢游玩，欢迎再来一局"],
                self.result_buttons(), view.OK_COLOR,
                hovered=self._hover_button,
            )

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
