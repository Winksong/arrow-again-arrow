"""路径检测 / 边界 / 空格 相关测试。

对应 Step 2。重点覆盖两个坑：
    1. 先取下一格再判越界 → 负下标绕回棋盘另一端（T03）；
    2. flying 状态的箭头仍被当作阻挡。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from game.model import FLYING, Board


def make_board(rows, cols, spec):
    return Board.from_spec(rows, cols, spec)


# --------------------------------------------------------------------------
# 边界
# --------------------------------------------------------------------------

def test_in_bounds_rejects_negative():
    b = make_board(3, 3, [])
    assert b.in_bounds(0, 0)
    assert b.in_bounds(2, 2)
    # 关键：负数必须判为越界，不能依赖 list 负下标
    assert not b.in_bounds(-1, 0)
    assert not b.in_bounds(0, -1)
    assert not b.in_bounds(3, 0)
    assert not b.in_bounds(0, 3)


@pytest.mark.parametrize("direction", ["up", "down", "left", "right"])
def test_edge_arrow_path_stops_at_border(direction):
    """贴着边缘、朝棋盘外的箭头，路径必须为空且不越界。

    这正是 T03 要考的点：若先取下一格再判越界，
    这里会产出 (-1, c) 之类的坐标，甚至绕到另一端。
    """
    corners = {
        "up": (0, 1),
        "down": (2, 1),
        "left": (1, 0),
        "right": (1, 2),
    }
    r, c = corners[direction]
    b = make_board(3, 3, [(r, c, direction)])
    a = b.arrow_raw(r, c)

    path = list(b.iter_path(a))
    assert path == [], f"{direction} 贴边箭头不应有路径格"
    for pr, pc in path:
        assert b.in_bounds(pr, pc), "路径不应越界"
    assert b.path_clear(a), "贴边朝外的箭头应可飞出"


def test_path_never_contains_out_of_bounds_for_up_and_left():
    """对棋盘上每一个格、每一个方向，路径坐标必须全部在棋盘内。"""
    b = make_board(4, 4, [])
    for r in range(4):
        for c in range(4):
            for d in ("up", "down", "left", "right"):
                probe = make_board(4, 4, [(r, c, d)]).arrow_raw(r, c)
                for pr, pc in b.iter_path(probe):
                    assert 0 <= pr < 4 and 0 <= pc < 4


# --------------------------------------------------------------------------
# 阻挡判定
# --------------------------------------------------------------------------

def test_blocked_same_row():
    """同一行、正前方有箭头 → 被阻挡。"""
    b = make_board(1, 5, [(0, 0, "right"), (0, 3, "left")])
    assert not b.path_clear(b.arrow_raw(0, 0))
    assert b.blocking_arrow(b.arrow_raw(0, 0)) is b.arrow_raw(0, 3)


def test_blocked_same_col():
    """同一列、正前方有箭头 → 被阻挡。"""
    b = make_board(5, 1, [(0, 0, "down"), (3, 0, "up")])
    assert not b.path_clear(b.arrow_raw(0, 0))


def test_blocker_direction_is_irrelevant():
    """阻挡箭头的朝向不计 —— 它朝谁都不影响能否阻挡。"""
    for blocker_dir in ("up", "down", "left", "right"):
        b = make_board(3, 3, [(1, 0, "right"), (1, 1, blocker_dir)])
        assert not b.path_clear(b.arrow_raw(1, 0)), f"阻挡者朝 {blocker_dir}"


def test_gap_between_still_blocked():
    """中间隔空格仍被阻挡。"""
    b = make_board(1, 5, [(0, 0, "right"), (0, 4, "left")])
    assert not b.path_clear(b.arrow_raw(0, 0))


def test_different_row_and_col_do_not_block():
    """既不同行也不同列 → 不阻挡。"""
    b = make_board(3, 3, [(0, 0, "right"), (1, 1, "down")])
    assert b.path_clear(b.arrow_raw(0, 0))
    assert b.path_clear(b.arrow_raw(1, 1))


def test_arrow_behind_does_not_block():
    """箭头背后的箭头不构成阻挡。"""
    b = make_board(1, 5, [(0, 4, "right"), (0, 2, "left")])
    a = b.arrow_raw(0, 4)   # 朝右，右边已是边界
    assert b.path_clear(a)


# --------------------------------------------------------------------------
# flying 状态
# --------------------------------------------------------------------------

def test_flying_arrow_does_not_block():
    """flying 的箭头逻辑上已消除，不应再阻挡别人。"""
    b = make_board(1, 5, [(0, 0, "right"), (0, 3, "left")])
    assert not b.path_clear(b.arrow_raw(0, 0))

    b.arrow_raw(0, 3).state = FLYING
    assert b.path_clear(b.arrow_raw(0, 0)), "飞出中的箭头不该继续阻挡"


def test_flying_arrow_not_clickable():
    """flying 的箭头不应被再次点击到。"""
    b = make_board(3, 3, [(1, 1, "up")])
    assert b.arrow_at(1, 1) is not None
    b.arrow_raw(1, 1).state = FLYING
    assert b.arrow_at(1, 1) is None


def test_flying_arrow_not_counted_in_remaining():
    b = make_board(3, 3, [(1, 1, "up"), (2, 2, "down")])
    assert b.remaining() == 2
    b.arrow_raw(1, 1).state = FLYING
    assert b.remaining() == 1
    assert not b.is_empty()


# --------------------------------------------------------------------------
# 空格与查询
# --------------------------------------------------------------------------

def test_empty_cell_returns_none():
    b = make_board(3, 3, [(1, 1, "up")])
    assert b.arrow_at(0, 0) is None
    assert b.arrow_raw(0, 0) is None


def test_blocked_count():
    """初始被阻挡箭头数：用于关卡筛选，不能为 0。"""
    b = make_board(3, 3, [(0, 0, "right"), (0, 2, "up")])
    assert b.blocked_count() == 1
    assert make_board(3, 3, [(0, 0, "up")]).blocked_count() == 0


def test_snapshot_roundtrip():
    """快照只含坐标与方向，可完整还原布局。"""
    spec = [(0, 0, "right"), (1, 2, "down")]
    b = make_board(3, 3, spec)
    snap = b.snapshot()
    assert sorted(snap) == sorted(spec)

    restored = Board.from_spec(3, 3, snap)
    assert sorted(restored.snapshot()) == sorted(spec)
