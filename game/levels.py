"""固定关卡数据（Step 4 实现）。

纯数据，方便调参与测试。棋盘用字符串表示：
    ↑ ↓ ← →  为箭头，· 为空格
"""

from __future__ import annotations

# 关卡布局字符 → 方向
GLYPH_TO_DIR: dict[str, str] = {
    "↑": "up",
    "↓": "down",
    "←": "left",
    "→": "right",
}

# Step 4 填入真实关卡；此处先留空，避免误用过期的占位数据
LEVELS: list[dict] = []
