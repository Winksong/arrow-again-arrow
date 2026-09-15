"""规则与数据层。

约束：本模块 **不 import pygame**，保证逻辑可被自动化测试直接调用。

判定规则（来自作业要求，是本项目的核心考点）：
    只看**同一行或同一列**——检查箭头前进方向到棋盘边界之间
    是否存在其他箭头（中间可以隔空格；阻挡箭头的朝向不计）。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# 方向 → (行位移, 列位移)
DIRS: dict[str, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

# 箭头状态
IDLE = "idle"
FLYING = "flying"
BLOCKED = "blocked"


@dataclass
class Arrow:
    """棋盘上的一个箭头。"""

    row: int
    col: int
    direction: str          # "up" / "down" / "left" / "right"
    state: str = IDLE       # idle / flying / blocked
    anim_t: float = 0.0     # 动画进度（秒）

    def __post_init__(self) -> None:
        if self.direction not in DIRS:
            raise ValueError(f"非法方向：{self.direction!r}")

    def __hash__(self) -> int:
        # 按身份哈希：同一格重建对象后仍可区分，避免 dataclass 默认行为
        # 在字段被就地修改（row/col/state）后导致哈希漂移。
        return id(self)

    @property
    def pos(self) -> tuple[int, int]:
        return (self.row, self.col)

    @property
    def delta(self) -> tuple[int, int]:
        """本箭头的前进位移。"""
        return DIRS[self.direction]


@dataclass
class Board:
    """棋盘：用 (row, col) → Arrow 的字典维护，按坐标取箭头 O(1)。"""

    rows: int
    cols: int
    cells: dict[tuple[int, int], Arrow] = field(default_factory=dict)

    # ---------- 基础查询 ----------

    def in_bounds(self, r: int, c: int) -> bool:
        """坐标是否落在棋盘内。

        注意：Python 负下标不会报错，所以边界判断必须显式做，
        不能依赖 list 的越界检查。
        """
        return 0 <= r < self.rows and 0 <= c < self.cols

    def arrow_at(self, r: int, c: int) -> Arrow | None:
        """取该格**参与判定**的箭头。

        flying 状态的箭头在逻辑上已经消除（正在播飞出动画），
        因此不算阻挡，也不应被再次点击。这是本项目第二个易错点。
        """
        a = self.cells.get((r, c))
        if a is None or a.state == FLYING:
            return None
        return a

    def arrow_raw(self, r: int, c: int) -> Arrow | None:
        """取该格箭头，忽略状态（供绘制层使用）。"""
        return self.cells.get((r, c))

    @property
    def arrows(self) -> list[Arrow]:
        """棋盘上的全部箭头（含 flying，供绘制层使用）。"""
        return list(self.cells.values())

    @property
    def active_arrows(self) -> list[Arrow]:
        """参与判定的箭头（不含 flying）。"""
        return [a for a in self.cells.values() if a.state != FLYING]

    def remaining(self) -> int:
        """剩余箭头数：flying 的已消除，不计入。"""
        return len(self.active_arrows)

    def is_empty(self) -> bool:
        """是否已清空（判定层面）。"""
        return self.remaining() == 0

    @property
    def positions(self) -> set[tuple[int, int]]:
        return set(self.cells)

    # ---------- 路径检测（Step 2 核心） ----------

    def iter_path(self, arrow: Arrow) -> Iterator[tuple[int, int]]:
        """沿箭头方向，逐个产出「从箭头相邻格到边界」之间的格子坐标。

        ✅ 边界判断放在 while 条件里 —— 先判后取。
        若写成「先取下一位、再判断越界」，向上/向左走到边界时会访问
        grid[-1]：Python 负下标不报错，会静默绕到棋盘另一端，
        导致判定出错且人工试玩几乎发现不了（对应测试项 T03）。
        """
        dr, dc = arrow.delta
        r, c = arrow.row + dr, arrow.col + dc
        while self.in_bounds(r, c):
            yield r, c
            r += dr
            c += dc

    def path_clear(self, arrow: Arrow) -> bool:
        """前方无阻挡 → 可以飞出棋盘。

        用 arrow_at() 过滤 flying 状态，保证「正在飞出的箭头不再挡别人」。
        """
        return not any(self.arrow_at(r, c) is not None for r, c in self.iter_path(arrow))

    def blocking_arrow(self, arrow: Arrow) -> Arrow | None:
        """返回第一个挡住它的箭头；无阻挡返回 None。"""
        for r, c in self.iter_path(arrow):
            other = self.arrow_at(r, c)
            if other is not None:
                return other
        return None

    def blocked_count(self) -> int:
        """初始被阻挡的箭头数量。

        用于关卡筛选：值为 0 说明开局没有任何阻挡，
        体现不出玩法（对应 Step 4 的筛选条件）。
        """
        return sum(1 for a in self.active_arrows if not self.path_clear(a))

    # ---------- 增删 ----------

    def add(self, arrow: Arrow) -> Arrow:
        if not self.in_bounds(arrow.row, arrow.col):
            raise ValueError(f"箭头位置越界：{arrow.pos}")
        if (arrow.row, arrow.col) in self.cells:
            raise ValueError(f"该格已有箭头：{arrow.pos}")
        self.cells[arrow.pos] = arrow
        return arrow

    def remove(self, arrow: Arrow) -> bool:
        """按位置移除指定箭头，返回是否真的移除了。"""
        cur = self.cells.get(arrow.pos)
        if cur is arrow:
            del self.cells[arrow.pos]
            return True
        return False

    def snapshot(self) -> list[tuple[int, int, str]]:
        """快照：只存坐标 + 方向，供撤销 / 重开使用。

        不存对象引用，避免恢复时旧对象仍被别处持有导致状态错乱。
        """
        return [(a.row, a.col, a.direction) for a in self.active_arrows]

    # ---------- 构造 ----------

    @classmethod
    def from_spec(cls, rows: int, cols: int, arrows: list[tuple[int, int, str]]) -> Board:
        board = cls(rows=rows, cols=cols)
        for r, c, d in arrows:
            board.add(Arrow(row=r, col=c, direction=d))
        return board
