"""试玩脚本测试。

确保 tools/playtest.py 本身可用，并且它的结论
（每关零失误可通关、难度递增）在关卡改动后仍成立。
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from game import levels          # noqa: E402
from game.model import STATE_SUCCESS  # noqa: E402


def _load_playtest():
    """把 tools/playtest.py 作为模块加载（它不是包的一部分）。"""
    path = ROOT / "tools" / "playtest.py"
    spec = importlib.util.spec_from_file_location("playtest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["playtest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def playtest():
    return _load_playtest()


# --------------------------------------------------------------------------
# 零失误通关
# --------------------------------------------------------------------------

@pytest.mark.parametrize("idx", range(len(levels.LEVELS)),
                         ids=lambda i: levels.LEVELS[i]["name"])
def test_perfect_play_wins_every_level(playtest, idx):
    """⭐ 每关都要能零失误通关（试玩脚本独立于 pytest 的第二道验证）。"""
    result = playtest.play_perfect(levels.LEVELS[idx])
    assert result["ok"], f"{levels.LEVELS[idx]['name']} 无法零失误通关：{result['reason']}"
    assert result["mistakes_left"] == levels.LEVELS[idx]["mistakes"]


def test_perfect_play_uses_all_arrows(playtest):
    for lv in levels.LEVELS:
        result = playtest.play_perfect(lv)
        assert result["steps"] == len(levels.level_arrows(lv)), (
            f"{lv['name']} 通关步数应等于箭头数"
        )


# --------------------------------------------------------------------------
# 随机试玩
# --------------------------------------------------------------------------

def test_random_play_terminates(playtest):
    """随机乱点必须能结束（不会死循环）。"""
    rng = random.Random(0)
    for lv in levels.LEVELS:
        r = playtest.play_random(lv, rng)
        assert r["clicks"] > 0
        assert 0 <= r["cleared"] <= len(levels.level_arrows(lv))
        assert r["mistakes_left"] >= 0


def test_random_play_sometimes_wins_first_level(playtest):
    """第 1 关是入门关，随机乱点应有相当比例能通关。"""
    rng = random.Random(42)
    wins = sum(playtest.play_random(levels.LEVELS[0], rng)["win"]
               for _ in range(300))
    assert wins > 0, "第 1 关随机试玩从未通关，关卡可能过难"


def test_random_play_rarely_wins_hardest_level(playtest):
    """最后一关应明显更难。"""
    rng = random.Random(42)
    easy = sum(playtest.play_random(levels.LEVELS[0], rng)["win"]
               for _ in range(300))
    hard = sum(playtest.play_random(levels.LEVELS[-1], rng)["win"]
               for _ in range(300))
    assert hard < easy, "最后一关并未比第一关更难"


# --------------------------------------------------------------------------
# 难度递增
# --------------------------------------------------------------------------

def test_difficulty_increases(playtest):
    """难度应递增：箭头数递增，且随机通关率总体下降。"""
    results, _ = playtest.run_all(trials=400, seed=2026)

    counts = [r["arrows"] for r in results]
    assert counts == sorted(counts) and len(set(counts)) == len(counts), (
        f"箭头数应严格递增：{counts}"
    )

    rates = [r["random_win_rate"] for r in results]
    assert rates[0] > rates[-1], (
        f"首关通关率应高于末关：{rates[0]:.2%} vs {rates[-1]:.2%}"
    )
    # 允许小幅波动，但整体趋势必须下降
    assert rates[-1] < rates[0] * 0.5, (
        f"末关难度提升不明显：{rates}"
    )


def test_all_levels_perfect_in_report(playtest):
    results, _ = playtest.run_all(trials=100, seed=1)
    bad = [r["name"] for r in results if not r["perfect_ok"]]
    assert not bad, f"以下关卡无法零失误通关：{bad}"


# --------------------------------------------------------------------------
# 报告渲染
# --------------------------------------------------------------------------

def test_report_contains_key_sections(playtest):
    results, _ = playtest.run_all(trials=50, seed=3)
    report = playtest.render_report(results, 50)

    assert "表 1" in report
    assert "表 2" in report
    assert "难度递增检验" in report
    assert "零失误通关" in report
    for lv in levels.LEVELS:
        assert lv["name"] in report


def test_table_renderer_handles_cjk_width(playtest):
    """表格渲染要正确处理中文宽度（否则列会错位）。"""
    table = playtest.fmt_table([["中文", "ab"], ["短", "cdef"]], ["列一", "列二"])
    lines = table.splitlines()
    assert len(lines) == 4          # 表头 + 分隔线 + 2 行数据
    assert "列一" in lines[0]
    assert set(lines[1]) <= set("-+")
