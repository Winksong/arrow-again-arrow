"""关卡流程与结果界面测试（对应 T04 / T05 / T06）。

    T04 消除本关全部箭头 → 显示通关并进入下一关
    T05 失误次数耗尽     → 显示失败并允许重新开始
    T06 游戏进行中重新开始 → 箭头布局和失误次数恢复初始值
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from game import levels, view
from game.model import (
    STATE_FAILED,
    STATE_PLAYING,
    STATE_SUCCESS,
    Board,
    Session,
)
from game.solver import solve

STATE_START = "start"
STATE_ALLCLEAR = "allclear"


def make_app(level_index=0):
    from game.app import GameApp

    app = GameApp(level_index=level_index)
    app.state = STATE_PLAYING
    return app


def clear_level(app):
    """按求解器的解，把当前关打通。"""
    order = solve(
        [(a.row, a.col, a.direction) for a in app.board.active_arrows],
        app.board.rows, app.board.cols,
    )
    assert order is not None
    for r, c, _d in order:
        app._on_board_click(app.layout.cell_center(r, c))
        app._update_animations(view.FLY_DURATION + 0.01)
    return order


# --------------------------------------------------------------------------
# T04 通关并进入下一关
# --------------------------------------------------------------------------

def test_t04_clear_level_shows_success():
    app = make_app(0)
    try:
        clear_level(app)
        assert app.board.is_empty()
        assert app.session.state == STATE_SUCCESS
        assert app.state == STATE_SUCCESS, "应进入通关界面"
        assert app.in_result_screen is True
    finally:
        app.shutdown()


def test_t04_success_screen_renders_without_error():
    app = make_app(0)
    try:
        clear_level(app)
        app.draw()          # 通关卡片必须能画出来
    finally:
        app.shutdown()


def test_t04_next_level_advances():
    """点「下一关」应进入下一关，且状态回到 playing。"""
    app = make_app(0)
    try:
        clear_level(app)
        assert app.state == STATE_SUCCESS

        btn = next(b for b in app.result_buttons() if b.text == "下一关")
        result = app.on_click(btn.rect.center)

        assert result == "next_level"
        assert app.level_index == 1, "关卡索引应 +1"
        assert app.state == STATE_PLAYING
        assert app.session.state == STATE_PLAYING
        assert app.session.mistakes_left == app.initial_mistakes
        assert app.board.remaining() > 0, "新关卡应有箭头"
    finally:
        app.shutdown()


def test_t04_last_level_goes_to_allclear():
    """最后一关通关后，应进入全通关界面而不是"下一关"。"""
    last = levels.level_count() - 1
    app = make_app(last)
    try:
        clear_level(app)
        assert app.state == STATE_SUCCESS

        btn = next(b for b in app.result_buttons() if b.text == "下一关")
        app.on_click(btn.rect.center)

        assert app.state == STATE_ALLCLEAR
        app.draw()
    finally:
        app.shutdown()


def test_t04_result_screen_blocks_board_clicks():
    """结果界面出现后，底层棋盘不应再响应点击。"""
    app = make_app(0)
    try:
        clear_level(app)
        assert app.state == STATE_SUCCESS

        # 强行往棋盘上点，状态不应被改动
        before = app.state
        app.on_click(app.layout.cell_center(0, 0))
        assert app.state == before
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# T05 失误耗尽 → 失败并允许重开
# --------------------------------------------------------------------------

def test_t05_fail_when_mistakes_exhausted():
    from game.app import GameApp

    # 用一个小棋盘：两个箭头互相指着，怎么点都是失误
    app = GameApp(session=Session(
        board=Board.from_spec(1, 3, [(0, 0, "right"), (0, 2, "left")]),
        mistakes_left=2,
    ))
    app.state = STATE_PLAYING
    try:
        for _ in range(2):
            app._on_board_click(app.layout.cell_center(0, 0))
            app._update_animations(view.BLOCK_DURATION + 0.01)
            # 反复点 (0,0)：它朝右，被 (0,2) 挡着，必定失误

        assert app.session.mistakes_left == 0
        assert app.session.state == STATE_FAILED
        assert app.state == STATE_FAILED, "应进入失败界面"
    finally:
        app.shutdown()


def test_t05_failure_screen_renders():
    from game.app import GameApp

    app = GameApp(session=Session(
        board=Board.from_spec(1, 3, [(0, 0, "right"), (0, 2, "left")]),
        mistakes_left=1,
    ))
    app.state = STATE_PLAYING
    try:
        app._on_board_click(app.layout.cell_center(0, 0))
        app._update_animations(view.BLOCK_DURATION + 0.01)
        assert app.state == STATE_FAILED
        app.draw()
    finally:
        app.shutdown()


def test_t05_restart_from_failure_screen():
    """失败界面上点「重开本关」应恢复初始布局与失误次数。"""
    from game.app import GameApp

    app = GameApp(session=Session(
        board=Board.from_spec(1, 3, [(0, 0, "right"), (0, 2, "left")]),
        mistakes_left=1,
    ))
    app.state = STATE_PLAYING
    try:
        app._on_board_click(app.layout.cell_center(0, 0))
        app._update_animations(view.BLOCK_DURATION + 0.01)
        assert app.state == STATE_FAILED

        btn = next(b for b in app.result_buttons() if b.text == "重开本关")
        result = app.on_click(btn.rect.center)

        assert result == "restart"
        assert app.state == STATE_PLAYING
        assert app.session.mistakes_left == app.initial_mistakes
        assert not app.session.is_over()
    finally:
        app.shutdown()


def test_t05_back_to_start_from_failure():
    from game.app import GameApp

    app = GameApp(session=Session(
        board=Board.from_spec(1, 3, [(0, 0, "right"), (0, 2, "left")]),
        mistakes_left=1,
    ))
    app.state = STATE_PLAYING
    try:
        app._on_board_click(app.layout.cell_center(0, 0))
        app._update_animations(view.BLOCK_DURATION + 0.01)

        btn = next(b for b in app.result_buttons() if b.text == "返回开始")
        app.on_click(btn.rect.center)
        assert app.state == STATE_START
    finally:
        app.shutdown()


# --------------------------------------------------------------------------
# T06 游戏进行中重新开始
# --------------------------------------------------------------------------

def test_t06_restart_restores_initial_state():
    app = make_app(1)      # 第 2 关
    try:
        before_arrows = app.board.remaining()
        before_mistakes = app.session.mistakes_left
        assert before_arrows > 0

        # 消除一个箭头 + 制造一次失误
        free = next(a for a in app.board.active_arrows if app.board.path_clear(a))
        app._on_board_click(app.layout.cell_center(free.row, free.col))
        app._update_animations(view.FLY_DURATION + 0.01)
        assert app.board.remaining() == before_arrows - 1

        blocked = next(a for a in app.board.active_arrows
                       if not app.board.path_clear(a))
        app._on_board_click(app.layout.cell_center(blocked.row, blocked.col))
        app._update_animations(view.BLOCK_DURATION + 0.01)
        assert app.session.mistakes_left == before_mistakes - 1

        # 重开
        app.restart()

        assert app.board.remaining() == before_arrows, "箭头布局应恢复"
        assert app.session.mistakes_left == before_mistakes, "失误次数应恢复"
        assert app.session.state == STATE_PLAYING
        assert app.state == STATE_PLAYING
        assert not app.animating, "动画状态应清空"
        assert app._floats == []
        assert app._banner is None
    finally:
        app.shutdown()


def test_t06_restart_via_key():
    """按 R 键也应能重开（游戏进行中）。"""
    app = make_app(0)
    try:
        free = next(a for a in app.board.active_arrows if app.board.path_clear(a))
        app._on_board_click(app.layout.cell_center(free.row, free.col))
        app._update_animations(view.FLY_DURATION + 0.01)
        remaining_after = app.board.remaining()

        event = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r})
        app.handle_event(event)

        assert app.board.remaining() > remaining_after, "R 键应重开本关"
    finally:
        app.shutdown()


def test_t06_restart_layout_matches_level_data():
    """重开后的布局应与关卡数据完全一致。"""
    for idx in range(levels.level_count()):
        app = make_app(idx)
        try:
            expected = sorted(levels.level_arrows(app.level))
            # 先破坏一下
            free = next((a for a in app.board.active_arrows
                         if app.board.path_clear(a)), None)
            if free is not None:
                app._on_board_click(app.layout.cell_center(free.row, free.col))
                app._update_animations(view.FLY_DURATION + 0.01)

            app.restart()
            got = sorted((a.row, a.col, a.direction) for a in app.board.active_arrows)
            assert got == expected, f"第 {idx+1} 关重开后布局不一致"
        finally:
            app.shutdown()


# --------------------------------------------------------------------------
# 开始界面与关卡装载
# --------------------------------------------------------------------------

def test_start_screen_then_start_game():
    from game.app import GameApp

    app = GameApp(level_index=0)
    try:
        assert app.state == STATE_START
        app.draw()      # 开始界面能画

        btn = next(b for b in app.result_buttons() if b.text == "开始游戏")
        app.on_click(btn.rect.center)
        assert app.state == STATE_PLAYING
        assert app.board.remaining() > 0
    finally:
        app.shutdown()


def test_load_each_level():
    for idx in range(levels.level_count()):
        app = make_app(idx)
        try:
            assert app.level_index == idx
            assert app.board.rows == app.level["rows"]
            assert app.board.cols == app.level["cols"]
            assert app.session.mistakes_left == app.level["mistakes"]
            app.draw()
        finally:
            app.shutdown()


def test_full_playthrough_all_levels():
    """从第 1 关一路打到全通关，确认关卡衔接不出错。"""
    app = make_app(0)
    try:
        for _ in range(levels.level_count()):
            clear_level(app)
            assert app.state == STATE_SUCCESS
            btn = next(b for b in app.result_buttons() if b.text == "下一关")
            app.on_click(btn.rect.center)

        assert app.state == STATE_ALLCLEAR
        app.draw()
    finally:
        app.shutdown()


def test_card_buttons_do_not_overlap_card_bounds():
    """按钮必须落在卡片内部，否则会跑到棋盘上（结果界面布局坑）。"""
    for state in (STATE_SUCCESS, STATE_FAILED, STATE_ALLCLEAR, STATE_START):
        app = make_app(0)
        try:
            app.state = state
            card = view.card_layout((900, 700))
            for btn in app.result_buttons():
                assert card.contains(btn.rect), (
                    f"状态 {state} 的按钮 {btn.text} 超出卡片范围：{btn.rect} vs {card}"
                )
        finally:
            app.shutdown()
