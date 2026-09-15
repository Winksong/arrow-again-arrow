"""关卡试玩脚本。

对每一关做两件事并输出表格：
    1. **只用正确操作通关** → 验证能否零失误通过；
    2. **随机乱点 N 次**     → 统计通关率，用来衡量难度是否递增。

用法：
    python tools/playtest.py                # 默认每关随机试玩 2000 局
    python tools/playtest.py --trials 5000  # 自定义局数
    python tools/playtest.py --seed 42      # 固定随机种子，结果可复现
    python tools/playtest.py --json out.json  # 额外导出 JSON

注意：本脚本**不使用 pygame**，直接驱动逻辑层 Session，
因此无需显示器与声卡，可在任何环境运行。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# 允许从项目根目录或 tools/ 目录运行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game import levels                                    # noqa: E402
from game.model import (                                   # noqa: E402
    STATE_FAILED,
    STATE_SUCCESS,
    Board,
    Session,
)
from game.solver import count_blocked, direction_kinds, solve  # noqa: E402


# --------------------------------------------------------------------------
# 单局试玩
# --------------------------------------------------------------------------

def build_session(level: dict) -> Session:
    return Session(
        board=Board.from_spec(
            level["rows"], level["cols"], levels.level_arrows(level)
        ),
        mistakes_left=level["mistakes"],
    )


def play_perfect(level: dict) -> dict:
    """按求解器的解，零失误通关一局。

    返回 {'ok': bool, 'steps': int, 'mistakes_left': int, 'reason': str}
    """
    session = build_session(level)
    order = solve(
        levels.level_arrows(level), level["rows"], level["cols"]
    )
    if order is None:
        return {"ok": False, "steps": 0,
                "mistakes_left": session.mistakes_left, "reason": "无解"}

    steps = 0
    for r, c, _d in order:
        result = session.click(r, c)
        if result != "fly":
            return {"ok": False, "steps": steps,
                    "mistakes_left": session.mistakes_left,
                    "reason": f"按解点击 ({r}, {c}) 却被判定为 {result}"}

        arrow = session.board.arrow_raw(r, c)
        session.on_fly_finished(arrow)
        steps += 1

    # 全部走完后必须清空并通过
    if not session.board.is_empty():
        return {"ok": False, "steps": steps,
                "mistakes_left": session.mistakes_left, "reason": "未清空"}

    # 触发通关判定（on_fly_finished 里已置 success）
    if session.state != STATE_SUCCESS:
        return {"ok": False, "steps": steps,
                "mistakes_left": session.mistakes_left, "reason": "未进入通关状态"}

    return {"ok": True, "steps": steps,
            "mistakes_left": session.mistakes_left, "reason": ""}


def play_random(level: dict, rng: random.Random) -> dict:
    """随机乱点一局，直到通关或失误耗尽。

    返回 {'win': bool, 'clicks': int, 'cleared': int, 'mistakes_left': int}
    """
    session = build_session(level)
    rows, cols = level["rows"], level["cols"]
    total = session.arrows_total

    # 给一个合理上限，避免极端情况下空转
    max_clicks = total * 12 + 40
    clicks = 0

    while not session.is_over() and clicks < max_clicks:
        r = rng.randrange(rows)
        c = rng.randrange(cols)
        clicks += 1

        result = session.click(r, c)
        if result == "fly":
            session.on_fly_finished(session.board.arrow_raw(r, c))

    cleared = total - session.board.remaining()
    return {
        "win": session.state == STATE_SUCCESS,
        "clicks": clicks,
        "cleared": cleared,
        "mistakes_left": session.mistakes_left,
    }


# --------------------------------------------------------------------------
# 表格输出
# --------------------------------------------------------------------------

def fmt_table(rows: list[list[str]], headers: list[str]) -> str:
    """生成等宽对齐的文本表格（中文按 2 个字符宽度计算）。"""
    def width(s: str) -> int:
        return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)

    def pad(s: str, w: int) -> str:
        return s + " " * max(w - width(s), 0)

    all_rows = [headers] + rows
    widths = [max(width(r[i]) for r in all_rows) for i in range(len(headers))]

    lines = []
    head = " | ".join(pad(h, widths[i]) for i, h in enumerate(headers))
    lines.append(head)
    lines.append("-+-".join("-" * w for w in widths))
    for row in rows:
        lines.append(" | ".join(pad(cell, widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def run_all(trials: int, seed: int | None) -> tuple[list[dict], str]:
    rng = random.Random(seed)
    results: list[dict] = []

    for idx, level in enumerate(levels.LEVELS):
        arrows = levels.level_arrows(level)
        rows, cols = level["rows"], level["cols"]

        perfect = play_perfect(level)

        wins = 0
        click_sum = 0
        cleared_sum = 0
        for _ in range(trials):
            r = play_random(level, rng)
            if r["win"]:
                wins += 1
            click_sum += r["clicks"]
            cleared_sum += r["cleared"]

        results.append({
            "index": idx + 1,
            "name": level["name"],
            "rows": rows,
            "cols": cols,
            "arrows": len(arrows),
            "mistakes": level["mistakes"],
            "blocked_initial": count_blocked(arrows, rows, cols),
            "directions": len(direction_kinds(arrows)),
            "perfect_ok": perfect["ok"],
            "perfect_steps": perfect["steps"],
            "perfect_mistakes_left": perfect["mistakes_left"],
            "perfect_reason": perfect["reason"],
            "trials": trials,
            "random_wins": wins,
            "random_win_rate": wins / trials if trials else 0.0,
            "avg_clicks": click_sum / trials if trials else 0.0,
            "avg_cleared": cleared_sum / trials if trials else 0.0,
        })

    return results, rng


def render_report(results: list[dict], trials: int) -> str:
    out: list[str] = []
    out.append("=" * 78)
    out.append("一箭又一箭 · 关卡试玩报告")
    out.append("=" * 78)
    out.append("")

    # 表 1：零失误通关验证
    out.append("【表 1】每关零失误通关验证（按求解器的解依次点击）")
    out.append("")
    rows = []
    for r in results:
        rows.append([
            r["name"],
            f"{r['rows']}x{r['cols']}",
            str(r["arrows"]),
            str(r["blocked_initial"]),
            str(r["directions"]),
            "通过" if r["perfect_ok"] else "失败",
            str(r["perfect_steps"]),
            f"{r['perfect_mistakes_left']}/{r['mistakes']}",
        ])
    out.append(fmt_table(rows, [
        "关卡", "棋盘", "箭头", "开局被挡", "方向种类",
        "零失误通关", "步数", "剩余失误",
    ]))
    out.append("")

    # 表 2：随机乱点通关率
    out.append(f"【表 2】随机乱点通关率（每关 {trials} 局）")
    out.append("")
    rows = []
    for r in results:
        rows.append([
            r["name"],
            f"{r['rows']}x{r['cols']}",
            str(r["arrows"]),
            str(trials),
            str(r["random_wins"]),
            f"{r['random_win_rate'] * 100:.2f}%",
            f"{r['avg_clicks']:.1f}",
            f"{r['avg_cleared']:.1f}/{r['arrows']}",
        ])
    out.append(fmt_table(rows, [
        "关卡", "棋盘", "箭头", "试玩局数", "通关局数",
        "通关率", "平均点击数", "平均消除",
    ]))
    out.append("")

    # 难度递增结论
    out.append("【难度递增检验】")
    out.append("")
    rates = [r["random_win_rate"] for r in results]
    counts = [r["arrows"] for r in results]
    out.append(f"  箭头数量序列   : {counts}  （应递增）")
    out.append(f"  随机通关率序列 : {[f'{x*100:.1f}%' for x in rates]}")
    strictly_down = all(
        rates[i] < rates[i - 1] for i in range(1, len(rates))
    )
    if strictly_down:
        out.append("  结论           : 通关率随关卡严格下降，难度递增成立 ✅")
    else:
        out.append("  结论           : 通关率未严格递减，需检查关卡设计 ⚠️")
    out.append("")

    # 失败原因
    bad = [r for r in results if not r["perfect_ok"]]
    if bad:
        out.append("【零失误通关失败】")
        for r in bad:
            out.append(f"  {r['name']}: {r['perfect_reason']}")
        out.append("")

    out.append("=" * 78)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="一箭又一箭 —— 关卡试玩脚本"
    )
    parser.add_argument("--trials", type=int, default=2000,
                        help="每关随机试玩局数（默认 2000）")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子，固定后结果可复现")
    parser.add_argument("--json", type=str, default=None,
                        help="把结果额外导出为 JSON 文件")
    args = parser.parse_args()

    if args.trials <= 0:
        print("--trials 必须为正整数")
        return 2

    results, _rng = run_all(args.trials, args.seed)
    report = render_report(results, args.trials)
    print(report)

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON 已导出：{path}")

    # 只要有一关零失误通不过，就以非零码退出（便于 CI 拦截）
    return 0 if all(r["perfect_ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
