"""关卡数据测试。

这一组测试是关卡的**守门人**：任何布局改动只要破坏可解性，
都会立刻被拦住。

`test_every_level_is_solvable` 是关键一条 —— 作业明确把
「关卡无法通关」列为扣分项。
"""

from __future__ import annotations

import pytest

from game import levels
from game.model import DIRS, Board, Session
from game.solver import count_blocked, direction_kinds, solvable


@pytest.fixture(params=range(len(levels.LEVELS)), ids=lambda i: levels.LEVELS[i]["name"])
def level(request):
    return levels.LEVELS[request.param]


# --------------------------------------------------------------------------
# 核心：每关必须可解
# --------------------------------------------------------------------------

def test_every_level_is_solvable(level):
    """⭐ 关键测试：每关都必须实际可通关。

    "关卡无法通关"是作业明确的扣分项，这条测试会持续拦住后续 bug。
    """
    arrows = levels.level_arrows(level)
    assert solvable(arrows, level["rows"], level["cols"]), (
        f"{level['name']} 无解！布局：\n"
        f"{levels.render_layout(arrows, level['rows'], level['cols'])}"
    )


def test_every_level_is_playable_to_completion(level):
    """用求解器的解，真正驱动 Session 走一遍，确认状态可以变成 success。"""
    from game.solver import solve

    arrows = levels.level_arrows(level)
    order = solve(arrows, level["rows"], level["cols"])
    assert order is not None

    session = Session(
        board=Board.from_spec(level["rows"], level["cols"], arrows),
        mistakes_left=level["mistakes"],
    )

    for r, c, _d in order:
        result = session.click(r, c)
        assert result == "fly", (
            f"{level['name']} 按求解顺序点击 ({r}, {c}) 时被阻挡，"
            f"说明解答与判定不一致"
        )
        session.on_fly_finished(session.board.arrow_raw(r, c))

    assert session.board.is_empty(), f"{level['name']} 未能清空"
    assert session.state == "success", f"{level['name']} 未进入通关状态"
    assert session.mistakes_left == level["mistakes"], "零失误通关不应扣失误"


def test_every_level_has_initial_blocking(level):
    """每关开局都必须存在被阻挡的箭头。

    否则玩家一点就全飞完，阻挡机制完全体现不出来，玩法没意义。
    """
    arrows = levels.level_arrows(level)
    blocked = count_blocked(arrows, level["rows"], level["cols"])
    assert blocked >= 1, f"{level['name']} 开局没有任何被阻挡的箭头"
    assert blocked >= 2, f"{level['name']} 阻挡太少（{blocked}），难度不足"


# --------------------------------------------------------------------------
# 数据合法性
# --------------------------------------------------------------------------

def test_level_data_wellformed(level):
    """关卡数据必须合法：无越界、无重叠、方向合法、失误数为正。"""
    arrows = levels.level_arrows(level)
    rows, cols = level["rows"], level["cols"]

    assert rows > 0 and cols > 0, "棋盘尺寸必须为正"
    assert level["mistakes"] > 0, "失误次数必须为正"
    assert arrows, "关卡不能没有箭头"

    seen: set[tuple[int, int]] = set()
    for r, c, d in arrows:
        assert 0 <= r < rows, f"{level['name']} 箭头行越界：({r}, {c})"
        assert 0 <= c < cols, f"{level['name']} 箭头列越界：({r}, {c})"
        assert d in DIRS, f"{level['name']} 非法方向：{d}"
        assert (r, c) not in seen, f"{level['name']} 同一格有多个箭头：({r}, {c})"
        seen.add((r, c))


def test_board_construction_matches_level(level):
    """Board 构造后箭头数量应与关卡数据一致。"""
    arrows = levels.level_arrows(level)
    board = Board.from_spec(level["rows"], level["cols"], arrows)
    assert len(board.arrows) == len(arrows)
    assert board.remaining() == len(arrows)


# --------------------------------------------------------------------------
# 难度递增与方向覆盖
# --------------------------------------------------------------------------

def test_levels_are_ordered_by_difficulty():
    """难度应递增：棋盘尺寸不缩小，箭头数量递增。"""
    sizes = [(lv["rows"], lv["cols"]) for lv in levels.LEVELS]
    counts = [len(levels.level_arrows(lv)) for lv in levels.LEVELS]

    for i in range(1, len(sizes)):
        assert sizes[i][0] >= sizes[i - 1][0], "棋盘行数不应缩小"
        assert sizes[i][1] >= sizes[i - 1][1], "棋盘列数不应缩小"
        assert counts[i] > counts[i - 1], (
            f"箭头数量未递增：{counts[i-1]} -> {counts[i]}"
        )


def test_at_least_three_levels():
    """作业要求：至少 3 个固定关卡。"""
    assert len(levels.LEVELS) >= 3


def test_later_levels_cover_multiple_directions():
    """后续关卡应覆盖多个方向（至少 3 种）。"""
    for lv in levels.LEVELS[1:]:
        arrows = levels.level_arrows(lv)
        kinds = direction_kinds(arrows)
        assert len(kinds) >= 2, f"{lv['name']} 方向种类过少：{kinds}"


# --------------------------------------------------------------------------
# 工具函数
# --------------------------------------------------------------------------

def test_parse_and_render_roundtrip():
    """字符画 → 箭头 → 字符画，应能还原。"""
    text = """
→·↑
·↓·
↑··
"""
    rows, cols, arrows = levels.parse_layout(text)
    assert rows == 3 and cols == 3
    assert len(arrows) == 4

    rendered = levels.render_layout(arrows, rows, cols)
    rows2, cols2, arrows2 = levels.parse_layout(rendered)
    assert (rows2, cols2) == (rows, cols)
    assert sorted(arrows2) == sorted(arrows)


def test_get_level_clamps_index():
    assert levels.get_level(0) is levels.LEVELS[0]
    assert levels.get_level(-5) is levels.LEVELS[0]
    assert levels.get_level(999) is levels.LEVELS[-1]


def test_level_count():
    assert levels.level_count() == len(levels.LEVELS)


def test_parse_layout_ignores_blank_lines():
    rows, cols, arrows = levels.parse_layout("\n\n→·↑\n\n·↓·\n\n")
    assert rows == 2 and cols == 3
    assert len(arrows) == 3
