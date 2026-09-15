"""点击判定测试（对应 Step 4）。

覆盖 T01 / T02 / T03 的逻辑层部分：
    T01 点击前方无阻挡的箭头   → 标记飞出，剩余箭头数 -1
    T02 点击前方有阻挡的箭头   → 不消失，失误次数 -1
    T03 点击边缘朝外的箭头     → 正常飞出，不发生越界错误

这里直接驱动 Session + 构造真实 MOUSEBUTTONDOWN 事件两条路径都测，
确保「屏幕坐标 → 格子坐标 → 判定」整条链路可用。
"""

from __future__ import annotations

import pygame
import pytest

from game.model import (
    CLICK_BLOCKED,
    CLICK_EMPTY,
    CLICK_FLY,
    FLYING,
    STATE_FAILED,
    STATE_PLAYING,
    STATE_SUCCESS,
    Board,
    Session,
)


def make_session(rows, cols, spec, mistakes=3):
    return Session(board=Board.from_spec(rows, cols, spec), mistakes_left=mistakes)


# --------------------------------------------------------------------------
# T01 点击前方无阻挡的箭头 → 飞出
# --------------------------------------------------------------------------

def test_t01_click_free_arrow_flying():
    s = make_session(3, 3, [(1, 1, "up")])
    assert s.board.remaining() == 1

    result = s.click(1, 1)
    assert result == CLICK_FLY
    assert s.board.arrow_raw(1, 1).state == FLYING
    # flying 不计入剩余
    assert s.board.remaining() == 0
    assert s.mistakes_left == 3, "飞出不扣失误"


def test_t01_fly_finished_removes_arrow():
    s = make_session(3, 3, [(1, 1, "up")])
    s.click(1, 1)
    a = s.board.arrow_raw(1, 1)
    s.on_fly_finished(a)

    assert s.board.arrow_raw(1, 1) is None, "动画结束后箭头应从棋盘移除"
    assert s.board.is_empty()


def test_t01_fly_does_not_deduct_mistake():
    s = make_session(3, 3, [(0, 0, "up"), (2, 2, "down")])
    for pos in [(0, 0), (2, 2)]:
        s.click(*pos)
        s.on_fly_finished(s.board.cells.get(pos))
    assert s.mistakes_left == 3


# --------------------------------------------------------------------------
# T02 点击前方有阻挡的箭头 → 不消失，失误 -1
# --------------------------------------------------------------------------

def test_t02_click_blocked_arrow():
    s = make_session(3, 3, [(0, 0, "right"), (0, 2, "left")])
    result = s.click(0, 0)

    assert result == CLICK_BLOCKED
    assert s.board.arrow_raw(0, 0) is not None, "被阻挡的箭头不能消失"
    assert s.board.arrow_raw(0, 0).state == "blocked"
    assert s.mistakes_left == 2, "失误次数应 -1"
    assert s.state == STATE_PLAYING


def test_t02_blocked_same_col():
    s = make_session(4, 4, [(0, 1, "down"), (3, 1, "up")])
    assert s.click(0, 1) == CLICK_BLOCKED
    assert s.mistakes_left == 2


def test_t02_blocked_ignores_blocker_direction():
    """阻挡者朝向无关 —— 四个方向都要能挡住。"""
    for d in ("up", "down", "left", "right"):
        s = make_session(3, 3, [(1, 0, "right"), (1, 1, d)])
        assert s.click(1, 0) == CLICK_BLOCKED, f"阻挡者朝 {d} 应能挡住"


# --------------------------------------------------------------------------
# T03 边缘朝外的箭头 → 正常飞出，不越界
# --------------------------------------------------------------------------

@pytest.mark.parametrize("pos,direction", [
    ((0, 1), "up"),
    ((2, 1), "down"),
    ((1, 0), "left"),
    ((1, 2), "right"),
])
def test_t03_edge_arrow_flies_out(pos, direction):
    s = make_session(3, 3, [(*pos, direction)])
    assert s.click(*pos) == CLICK_FLY, f"{direction} 贴边箭头应能飞出"

    a = s.board.arrow_raw(*pos)
    s.on_fly_finished(a)
    assert s.board.is_empty()


@pytest.mark.parametrize("pos,direction", [
    ((0, 0), "up"), ((0, 0), "left"),
    ((3, 3), "down"), ((3, 3), "right"),
])
def test_t03_corner_arrows_no_out_of_bounds(pos, direction):
    """角落朝外的箭头：不得因为负下标绕到棋盘另一端。"""
    s = make_session(4, 4, [(*pos, direction)])
    a = s.board.arrow_raw(*pos)
    # 路径必须为空；若实现有负下标 bug，这里会拿到别的格坐标
    assert list(s.board.iter_path(a)) == []
    assert s.click(*pos) == CLICK_FLY


# --------------------------------------------------------------------------
# 点空格 / 棋盘外
# --------------------------------------------------------------------------

def test_click_empty_cell_no_penalty():
    s = make_session(3, 3, [(0, 0, "up")])
    assert s.click(1, 1) == CLICK_EMPTY
    assert s.mistakes_left == 3, "点空格不扣失误"
    assert s.board.remaining() == 1


@pytest.mark.parametrize("pos", [(-1, 0), (0, -1), (3, 0), (0, 3), (99, 99)])
def test_click_out_of_bounds_no_penalty(pos):
    s = make_session(3, 3, [(0, 0, "up")])
    assert s.click(*pos) == CLICK_EMPTY
    assert s.mistakes_left == 3


# --------------------------------------------------------------------------
# 失误耗尽
# --------------------------------------------------------------------------

def test_mistakes_exhausted_fails():
    s = make_session(3, 3, [(0, 0, "right"), (0, 2, "left")], mistakes=2)
    assert s.click(0, 0) == CLICK_BLOCKED
    assert s.mistakes_left == 1

    assert s.click(0, 0) == CLICK_BLOCKED
    assert s.mistakes_left == 0
    assert s.state == STATE_FAILED


def test_mistakes_never_negative():
    """失误下限为 0，不能变成负数。"""
    s = make_session(3, 3, [(0, 0, "right"), (0, 2, "left")], mistakes=1)
    s.click(0, 0)
    assert s.mistakes_left == 0
    # 失败后再点，不应继续扣
    s.click(0, 0)
    assert s.mistakes_left == 0


# --------------------------------------------------------------------------
# 通关
# --------------------------------------------------------------------------

def test_clear_all_arrows_succeeds():
    s = make_session(3, 3, [(0, 0, "up"), (1, 1, "down"), (2, 2, "up")])
    for pos in [(0, 0), (1, 1), (2, 2)]:
        assert s.click(*pos) == CLICK_FLY
        s.on_fly_finished(s.board.cells.get(pos))

    assert s.board.is_empty()
    assert s.state == STATE_SUCCESS


def test_flying_arrow_does_not_block_others():
    """一个箭头飞出的瞬间，被它挡住的箭头应立刻可以飞出。"""
    # (0,0) 朝右，(0,1) 挡在它的路上；(0,1) 朝上可直接飞出
    s = make_session(1, 3, [(0, 0, "right"), (0, 1, "up")])
    assert s.board.path_clear(s.board.arrow_raw(0, 0)) is False

    assert s.click(0, 1) == CLICK_FLY
    # 它进入 flying 后就不再阻挡，(0,0) 立刻可以飞出
    assert s.board.path_clear(s.board.arrow_raw(0, 0)) is True
    assert s.click(0, 0) == CLICK_FLY


def test_mutually_blocking_arrows_reachable_after_first_leaves():
    """互相指着时，先让其中一个飞走，另一个就通了。"""
    s = make_session(1, 3, [(0, 0, "right"), (0, 1, "left")])
    # 两个互相阻挡
    assert s.click(0, 0) == CLICK_BLOCKED
    assert s.mistakes_left == 2

    # 让 (0,1) 飞出后，(0,0) 就不被挡了
    s2 = make_session(1, 3, [(0, 0, "right"), (0, 1, "left")])
    s2.board.arrow_raw(0, 1).state = FLYING   # 模拟它已被点走
    assert s2.click(0, 0) == CLICK_FLY


# --------------------------------------------------------------------------
# 由真实鼠标事件驱动（连同坐标换算一起测）
# --------------------------------------------------------------------------

def test_click_via_real_mouse_event_on_free_arrow():
    """构造真实 MOUSEBUTTONDOWN，按格子中心像素坐标投给 App。"""
    from game.app import GameApp

    app = GameApp()
    try:
        # 找一个开局就能飞出的箭头
        target = None
        for a in app.board.active_arrows:
            if app.board.path_clear(a):
                target = a
                break
        assert target is not None

        before = app.board.remaining()
        pos = app.layout.cell_center(target.row, target.col)
        event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}
        )
        app.state = "playing"
        app.handle_event(event)

        assert target.state == FLYING
        assert app.board.remaining() == before - 1
    finally:
        app.shutdown()


def test_click_via_real_mouse_event_ignores_right_button():
    """右键不应触发任何判定。"""
    from game.app import GameApp

    app = GameApp()
    try:
        target = None
        for a in app.board.active_arrows:
            if app.board.path_clear(a):
                target = a
                break
        assert target is not None

        pos = app.layout.cell_center(target.row, target.col)
        event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 3}
        )
        app.state = "playing"
        app.handle_event(event)

        assert target.state == "idle", "右键不应产生任何效果"
    finally:
        app.shutdown()


def test_click_outside_board_via_event_no_penalty():
    from game.app import GameApp

    app = GameApp()
    try:
        before = app.session.mistakes_left
        event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, {"pos": (5, 5), "button": 1}
        )
        app.state = "playing"
        app.handle_event(event)
        assert app.session.mistakes_left == before
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# 回归：飞出动画必须真的被登记
# --------------------------------------------------------------------------

def test_fly_animation_is_registered_and_removes_arrow():
    """回归测试。

    坑：click() 会把箭头置为 flying，而 arrow_at() 对 flying 返回 None，
    若在 click 之后才用 arrow_at() 取箭头，会拿到 None，
    导致飞出动画根本没被登记、箭头永远留在棋盘上。
    """
    from game.app import FLY_DURATION, GameApp

    app = GameApp()
    try:
        app.state = "playing"
        target = next(a for a in app.board.active_arrows if app.board.path_clear(a))
        pos = app.layout.cell_center(target.row, target.col)

        before = app.board.remaining()
        assert app.on_click(pos) == "fly"

        # 关键断言：动画已被登记
        assert target in app._flying, "飞出动画未被登记（arrow_at 返回 None 的坑）"
        assert app.animating is True

        # 推进动画到结束
        app._update_animations(FLY_DURATION + 0.01)
        assert app.board.arrow_raw(target.row, target.col) is None, "动画结束后应移除"
        assert app.board.remaining() == before - 1
        assert app.animating is False
    finally:
        app.shutdown()


def test_animation_locks_input():
    """动画播放期间点击应被忽略，防止连点刷失误。"""
    from game.app import GameApp

    app = GameApp()
    try:
        app.state = "playing"
        # 找一个被阻挡的箭头
        blocked = next(
            a for a in app.board.active_arrows if not app.board.path_clear(a)
        )
        pos = app.layout.cell_center(blocked.row, blocked.col)
        app.on_click(pos)
        assert app.animating is True

        before = app.session.mistakes_left
        assert app.on_click(pos) == "busy", "动画期间应返回 busy"
        assert app.session.mistakes_left == before, "动画期间不应再扣失误"
    finally:
        app.shutdown()
