"""可解性校验与求解器。

用途：任何关卡数据入库前，都必须先通过本模块校验，避免出现
「互相指着」的无解死局。

**血泪教训**：人工摆关卡极容易摆出互相指着的死循环，肉眼看不出来，
必须用程序校验。
"""

from __future__ import annotations

from .model import Board, DIRS


def _clear_in(
    pos: tuple[int, int],
    direction: str,
    occupied: set[tuple[int, int]],
    rows: int,
    cols: int,
) -> bool:
    """在给定的「仍存在箭头」集合下，判断 pos 处箭头前方是否无阻挡。

    与 Board.path_clear 同源逻辑：边界判断放在循环条件里，先判后取。
    """
    dr, dc = DIRS[direction]
    r, c = pos[0] + dr, pos[1] + dc
    while 0 <= r < rows and 0 <= c < cols:      # ✅ 先判后取
        if (r, c) in occupied:
            return False
        r += dr
        c += dc
    return True


def solve(arrows, rows: int, cols: int) -> list[tuple[int, int, str]] | None:
    """求出一个可行解，返回按消除顺序排列的箭头列表。

    arrows: 可迭代的 (row, col, direction)
    返回 None 表示无解。

    策略：贪心 —— 每轮挑一个当前前方无阻挡的箭头消除，重复到清空。
    若某轮找不到任何可消除的箭头，说明剩下的互相挡死了，无解。
    """
    remaining = list(arrows)
    order: list[tuple[int, int, str]] = []

    while remaining:
        occupied = {(r, c) for r, c, _ in remaining}
        pick_idx = None
        for i, (r, c, d) in enumerate(remaining):
            if _clear_in((r, c), d, occupied, rows, cols):
                pick_idx = i
                break

        if pick_idx is None:
            return None                     # 剩下的互相挡死，无解

        order.append(remaining.pop(pick_idx))

    return order


def solvable(arrows, rows: int, cols: int) -> bool:
    """关卡是否可解。

    ⚠️ 早期版本把循环上限写成 len(remaining)，而它每轮都会变小，
    大棋盘会在还没判完时提前退出，把**有解误判成无解**。
    这里改为「外层 while remaining」，语义上循环次数恒等于箭头总数。
    """
    total = len(list(arrows))
    if total == 0:
        return True

    remaining = list(arrows)
    cleared = 0

    # 循环次数固定为「箭头总数」：用 cleared 计数，不依赖 remaining 的长度
    while cleared < total:
        if not remaining:
            break
        occupied = {(r, c) for r, c, _ in remaining}
        pick_idx = None
        for i, (r, c, d) in enumerate(remaining):
            if _clear_in((r, c), d, occupied, rows, cols):
                pick_idx = i
                break
        if pick_idx is None:
            return False
        remaining.pop(pick_idx)
        cleared += 1

    return not remaining


def solve_board(board: Board) -> list[tuple[int, int, str]] | None:
    """对 Board 求解（按当前参与判定的箭头）。"""
    spec = [(a.row, a.col, a.direction) for a in board.active_arrows]
    return solve(spec, board.rows, board.cols)


def count_blocked(arrows, rows: int, cols: int) -> int:
    """初始被阻挡的箭头数量。

    用于关卡筛选：值为 0 说明开局没有任何阻挡，体现不出玩法。
    """
    items = list(arrows)
    occupied = {(r, c) for r, c, _ in items}
    return sum(
        1 for (r, c, d) in items
        if not _clear_in((r, c), d, occupied - {(r, c)}, rows, cols)
    )


def direction_kinds(arrows) -> set[str]:
    """关卡中用到的方向集合（筛选"四个方向都出现过"用）。"""
    return {d for _, _, d in arrows}


# --------------------------------------------------------------------------
# 反向构造：生成必有解的随机关卡
# --------------------------------------------------------------------------

def generate(rows: int, cols: int, count: int, rng=None,
             min_blocked: int = 3, max_tries: int = 4000):
    """反向构造一个有解的关卡布局。

    原理：按「拆除顺序的**逆序**」放置箭头。放第 k 个箭头时，
    棋盘上只有「会在它之后才被拆掉」的箭头，因此只要求新箭头的
    路径上没有它们即可。这样放置顺序的逆序就是一种可行解。

    返回 [(row, col, direction), ...]，失败返回 None。
    """
    import random

    rng = rng or random.Random()
    dirs = list(DIRS)

    for _ in range(max_tries):
        placed: list[tuple[int, int, str]] = []
        occupied: set[tuple[int, int]] = set()

        cells = [(r, c) for r in range(rows) for c in range(cols)]
        rng.shuffle(cells)

        for (r, c) in cells:
            if len(placed) >= count:
                break
            rng.shuffle(dirs)
            for d in dirs:
                if _clear_in((r, c), d, occupied, rows, cols):
                    placed.append((r, c, d))
                    occupied.add((r, c))
                    break

        if len(placed) < count:
            continue

        # 双保险：生成后再用求解器校验一遍
        if not solvable(placed, rows, cols):
            continue

        # 筛选：初始被阻挡的箭头要够多，否则体现不出玩法
        if count_blocked(placed, rows, cols) < min_blocked:
            continue

        return placed

    return None
