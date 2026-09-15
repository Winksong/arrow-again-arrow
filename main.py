"""一箭又一箭 —— 程序入口。

用法：
    python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许从任意目录启动：确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    """启动游戏主循环。"""
    import game

    try:
        import pygame  # noqa: F401
    except ImportError:  # pragma: no cover - 仅在依赖缺失时触发
        print("缺少依赖 pygame-ce，请先执行： pip install -r requirements.txt")
        return 1

    from game.app import run

    print(f"arrow-again-arrow v{game.__version__} 启动中……")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
