"""固定关卡数据。

纯数据，方便调参与测试。棋盘用字符串表示：
    ↑ ↓ ← →  为箭头，· 为空格

⚠️ **重要**：所有关卡均已通过 game.solver 的可解性校验，
且保证开局存在「被阻挡」的箭头（否则体现不出玩法）。
修改任何布局后，必须重新跑 `python -m pytest tests/test_levels.py`。

血泪教训：手工摆盘极容易摆出「互相指着」的无解死局，肉眼看不出来。
本项目在开发过程中手工设计了 9 个候选布局，其中 **7 个被求解器判定为无解**。
因此关卡数据一律先用反向构造（solver.generate）产出候选，再人工挑选调优。
"""

from __future__ import annotations

# 关卡布局字符 → 方向
GLYPH_TO_DIR: dict[str, str] = {
    "↑": "up",
    "↓": "down",
    "←": "left",
    "→": "right",
}
DIR_TO_GLYPH: dict[str, str] = {v: k for k, v in GLYPH_TO_DIR.items()}

EMPTY_GLYPH = "·"


def parse_layout(text: str) -> tuple[int, int, list[tuple[int, int, str]]]:
    """把字符画布局解析成 (rows, cols, [(row, col, direction), ...])。

    便于手工调整关卡：直接编辑下面的多行字符串即可。
    """
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    rows = len(lines)
    cols = max((len(ln) for ln in lines), default=0)

    arrows: list[tuple[int, int, str]] = []
    for r, line in enumerate(lines):
        for c, ch in enumerate(line):
            if ch in GLYPH_TO_DIR:
                arrows.append((r, c, GLYPH_TO_DIR[ch]))
    return rows, cols, arrows


def render_layout(arrows, rows: int, cols: int) -> str:
    """反向：把箭头列表渲染成字符画（调试 / 文档用）。"""
    grid = [[EMPTY_GLYPH] * cols for _ in range(rows)]
    for r, c, d in arrows:
        grid[r][c] = DIR_TO_GLYPH[d]
    return "\n".join("".join(row) for row in grid)


# --------------------------------------------------------------------------
# 关卡定义
# --------------------------------------------------------------------------
# 说明：
#   - 棋盘尺寸按 3x3 → 4x4 → 5x5 递增
#   - 箭头数量按 4 → 6 → 8 → 10 递增，难度平滑上升
#   - 每关失误上限 3 次
#   - 每关开局都有 2 个以上被阻挡的箭头
# --------------------------------------------------------------------------

LEVELS: list[dict] = [
    {
        "name": "第 1 关 · 入门",
        "rows": 3,
        "cols": 3,
        "mistakes": 3,
        "layout": """
→·↑
·↓·
↑··
""",
    },
    {
        "name": "第 2 关 · 进阶",
        "rows": 4,
        "cols": 4,
        "mistakes": 3,
        "layout": """
·↓··
↑·→→
··↑·
···↑
""",
    },
    {
        "name": "第 3 关 · 挑战",
        "rows": 5,
        "cols": 5,
        "mistakes": 3,
        "layout": """
··↑··
··↑·←
·↓←··
···←→
····←
""",
    },
    {
        "name": "第 4 关 · 试炼",
        "rows": 5,
        "cols": 5,
        "mistakes": 3,
        "layout": """
→·→↑·
→····
··←↑·
·↓···
↑↓·↓·
""",
    },
]


def get_level(index: int) -> dict:
    """按索引取关卡（越界返回最后一关）。"""
    if not LEVELS:
        raise RuntimeError("关卡数据为空")
    index = max(0, min(index, len(LEVELS) - 1))
    return LEVELS[index]


def level_count() -> int:
    return len(LEVELS)


def level_arrows(level: dict) -> list[tuple[int, int, str]]:
    """取关卡的箭头列表；支持 layout 字符串或 arrows 列表两种写法。"""
    if "arrows" in level:
        return list(level["arrows"])
    _, _, arrows = parse_layout(level["layout"])
    return arrows
