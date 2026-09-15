"""失误次数与碰撞反馈测试（对应 Step 5）。

覆盖：
    - 失误次数 UI 数据来源正确（初始值、扣减、不为负）
    - 碰撞反馈动画的插值函数（回弹 / 闪红 / 晃动）取值合理
    - 反馈期间锁输入
    - 重开后失误次数恢复初始值
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game import view
from game.model import BLOCKED, IDLE, STATE_FAILED, Board, Session


def make_app(mistakes=3):
    from game.app import GameApp

    app = GameApp(session=Session(
        board=Board.from_spec(3, 3, [(0, 0, "right"), (0, 2, "left")]),
        mistakes_left=mistakes,
    ))
    app.state = "playing"
    return app


# --------------------------------------------------------------------------
# 失误次数
# --------------------------------------------------------------------------

def test_initial_mistakes_recorded():
    app = make_app(mistakes=3)
    try:
        assert app.initial_mistakes == 3
        assert app.session.mistakes_left == 3
    finally:
        app.shutdown()


def test_mistake_deducted_on_blocked_click():
    app = make_app(mistakes=3)
    try:
        pos = app.layout.cell_center(0, 0)
        assert app.on_click(pos) == "blocked"
        assert app.session.mistakes_left == 2
    finally:
        app.shutdown()


def test_no_deduction_on_free_arrow():
    app = make_app(mistakes=3)
    try:
        # (0,2) 朝左被挡住；(0,0) 朝右被挡住。
        # 用一个独立的、前方无阻挡的棋盘来测。
        from game.app import GameApp

        app.shutdown()
        app = GameApp(session=Session(
            board=Board.from_spec(3, 3, [(0, 0, "up")]), mistakes_left=3
        ))
        app.state = "playing"
        assert app.on_click(app.layout.cell_center(0, 0)) == "fly"
        assert app.session.mistakes_left == 3
    finally:
        app.shutdown()


def test_mistakes_not_negative_through_ui():
    app = make_app(mistakes=1)
    try:
        pos = app.layout.cell_center(0, 0)
        assert app.on_click(pos) == "blocked"
        assert app.session.mistakes_left == 0
        assert app.session.state == STATE_FAILED

        # 动画播完后再点，也不应继续扣
        app._update_animations(view.BLOCK_DURATION + 0.01)
        app.on_click(pos)
        assert app.session.mistakes_left == 0
    finally:
        app.shutdown()


def test_restart_restores_mistakes():
    app = make_app(mistakes=3)
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert app.session.mistakes_left == 2

        app.restart()
        assert app.session.mistakes_left == 3, "重开应恢复初始失误次数"
        assert app.initial_mistakes == 3
        assert app.board.remaining() == 2, "重开应恢复箭头布局"
    finally:
        app.shutdown()


def test_restart_clears_animation_state():
    app = make_app(mistakes=3)
    try:
        app.on_click(app.layout.cell_center(0, 0))    # blocked
        assert app.animating is True

        app.restart()
        assert app.animating is False, "重开应清空动画状态"
        assert app._floats == []
        assert app._banner is None
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# 碰撞反馈动画
# --------------------------------------------------------------------------

def _arrow(direction="right"):
    from game.model import Arrow

    return Arrow(row=0, col=0, direction=direction)


def test_block_recoil_returns_to_origin():
    """回弹必须在动画结束时归零，否则箭头会永久偏移。"""
    a = _arrow("right")
    assert view.block_recoil(a, 0.0) == (0.0, 0.0)
    assert view.block_recoil(a, view.BLOCK_DURATION) == (0.0, 0.0)
    assert view.block_recoil(a, view.BLOCK_DURATION + 1) == (0.0, 0.0)


def test_block_recoil_pushes_along_direction():
    """回弹方向应与箭头前进方向一致（朝右 → 向右推）。"""
    t_early = view.BLOCK_DURATION * 0.12
    dx, dy = view.block_recoil(_arrow("right"), t_early)
    assert dx > 0, "朝右的箭头应向右回弹"
    assert abs(dy) < 1e-6

    dx, dy = view.block_recoil(_arrow("up"), t_early)
    assert dy < 0, "朝上的箭头应向上回弹"
    assert abs(dx) < 1e-6

    dx, dy = view.block_recoil(_arrow("left"), t_early)
    assert dx < 0

    dx, dy = view.block_recoil(_arrow("down"), t_early)
    assert dy > 0


def test_block_flash_range_and_decay():
    """闪红强度应在 0~1 之间，且随时间衰减到 0。"""
    assert 0.0 <= view.block_flash(0.0) <= 1.0
    assert view.block_flash(view.BLOCK_DURATION * 0.1) == pytest.approx(1.0)
    assert view.block_flash(view.BLOCK_DURATION) == 0.0

    # 单调递减（过了峰值之后）
    mid = view.block_flash(view.BLOCK_DURATION * 0.5)
    late = view.block_flash(view.BLOCK_DURATION * 0.8)
    assert mid > late > 0


def test_block_shake_bounded_and_zero_at_ends():
    """晃动偏移应有界，且首尾归零。"""
    a = _arrow("right")
    assert view.block_shake(0.0) == 0.0
    assert view.block_shake(view.BLOCK_DURATION) == 0.0

    for i in range(1, 20):
        t = view.BLOCK_DURATION * i / 20
        assert abs(view.block_shake(t)) <= 8.0, "晃动幅度应受控"


def test_collision_feedback_registered_on_block():
    """点击被挡的箭头要登记碰撞反馈。"""
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert len(app._blocking) == 1, "应登记一条碰撞反馈"
        arrow = next(iter(app._blocking))
        assert arrow.state == BLOCKED
        assert app.animating is True
    finally:
        app.shutdown()


def test_collision_feedback_clears_state_after_duration():
    """反馈播完后，箭头应恢复 idle，不再持续变红。"""
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        arrow = next(iter(app._blocking))

        app._update_animations(view.BLOCK_DURATION + 0.01)
        assert arrow.state == IDLE, "反馈结束后应恢复常态"
        assert app.animating is False
    finally:
        app.shutdown()


def test_input_locked_during_collision_feedback():
    """碰撞反馈期间点击应被忽略，防止连点刷失误。"""
    app = make_app(mistakes=3)
    try:
        pos = app.layout.cell_center(0, 0)
        app.on_click(pos)
        before = app.session.mistakes_left

        for _ in range(5):
            assert app.on_click(pos) == "busy"
        assert app.session.mistakes_left == before, "反馈期间不应重复扣失误"
    finally:
        app.shutdown()


def test_input_locked_during_fly_animation():
    app = make_app()
    try:
        from game.app import GameApp

        app.shutdown()
        app = GameApp(session=Session(
            board=Board.from_spec(3, 3, [(0, 0, "up"), (2, 2, "down")]),
            mistakes_left=3,
        ))
        app.state = "playing"

        app.on_click(app.layout.cell_center(0, 0))
        assert app.animating is True
        assert app.on_click(app.layout.cell_center(2, 2)) == "busy"
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# 浮动文字与横幅
# --------------------------------------------------------------------------

def test_float_text_added_on_block():
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert len(app._floats) == 1
        assert app._floats[0].text == "失误 -1"
    finally:
        app.shutdown()


def test_float_text_expires():
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert len(app._floats) == 1

        app._update_animations(view.FLOAT_DURATION + 0.05)
        assert app._floats == [], "浮动文字应到期消失"
    finally:
        app.shutdown()


def test_banner_shows_blocker_position():
    """横幅应指出被谁挡住，帮玩家理解规则。"""
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert app._banner is not None
        text, color, _t = app._banner
        assert "(0, 2)" in text, "应指出阻挡者坐标"
        assert color == view.DANGER
    finally:
        app.shutdown()


def test_banner_expires():
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))
        assert app._banner is not None

        app._update_animations(view.BANNER_DURATION + 0.05)
        assert app._banner is None
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# 渲染不崩
# --------------------------------------------------------------------------

def test_draw_with_all_feedback_states():
    """同时存在飞出、碰撞、浮动文字、横幅时，绘制不应报错。"""
    app = make_app()
    try:
        app.on_click(app.layout.cell_center(0, 0))     # blocked → 反馈 + 浮动 + 横幅
        app._update_animations(0.10)
        app.draw()

        # 再让一个箭头飞出，与碰撞反馈叠加
        from game.app import GameApp

        app.shutdown()
        app = GameApp(session=Session(
            board=Board.from_spec(3, 3, [(0, 0, "up"), (1, 1, "right"), (1, 2, "left")]),
            mistakes_left=3,
        ))
        app.state = "playing"
        app.on_click(app.layout.cell_center(0, 0))     # fly
        app._update_animations(0.10)
        app.draw()
    finally:
        app.shutdown()


def test_draw_mistake_hearts_all_states():
    """失误图标在各种剩余数量下都能画出来。"""
    surf = pygame.Surface((300, 60))
    for left in range(0, 4):
        rect = view.draw_mistake_hearts(surf, (10, 10), left, 3, pulse=0.5)
        assert rect.width > 0


def test_shutdown_is_idempotent_for_font_cache():
    app = make_app()
    try:
        app.draw()
    finally:
        app.shutdown()
    # 再次清理不应报错
    view.clear_font_cache()
