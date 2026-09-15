"""骨架自检：确认包结构与依赖在干净环境下可用。

这一条测试从第一天就存在，用来保证「别人克隆下来能跑」。
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 这些模块必须保持「纯逻辑」：不依赖 pygame，才能在无头环境下测试。
PURE_LOGIC_MODULES = ["game/model.py", "game/solver.py", "game/levels.py"]


def _imported_modules(path: Path) -> set[str]:
    """用 AST 提取模块的顶层 import，避免被注释/文档字符串里的文字误伤。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


def test_package_importable():
    import game

    assert game.__version__


def test_pygame_available():
    import pygame

    assert pygame.version.ver


def test_main_entry_callable():
    import main

    assert callable(main.main)


def test_logic_layer_does_not_depend_on_pygame():
    """架构守护：逻辑层不得 import pygame。

    这是「测试不需要显示器/声卡」的前提。一旦有人在 model.py 里
    顺手加一句 ``import pygame``，这条测试会立刻失败并指出是哪个文件。

    用 AST 而不是字符串匹配，是因为 model.py 的文档字符串里本来就
    写着「本模块不 import pygame」这句话，字符串匹配会自我误报。
    """
    offenders = []
    for rel in PURE_LOGIC_MODULES:
        imported = _imported_modules(ROOT / rel)
        # 只有真正的 import 才算；子模块形式（import pygame.foo）已被
        # _imported_modules 归一化成顶层名 "pygame"。
        if "pygame" in imported:
            offenders.append(rel)

    assert not offenders, (
        f"以下模块不应依赖 pygame，但检测到了 import：{offenders}。"
        "逻辑层必须保持纯净，否则自动化测试将需要显示器与声卡。"
    )


def test_logic_layer_imports_are_stdlib_only():
    """架构守护：逻辑层只依赖标准库与自身包。

    注意：包内模块既可能被写成 ``from game.model import ...``，
    也可能被写成 ``from model import ...``（取决于运行方式），
    所以自身包的模块名要单独列出，不能只靠 "game" 前缀判断。
    """
    own_package_modules = {"game", "model", "solver", "levels", "view", "app"}
    stdlib_ok = {
        "__future__",
        "collections",
        "dataclasses",
        "enum",
        "itertools",
        "math",
        "pathlib",
        "random",
        "typing",
    }
    unexpected = {}
    for rel in PURE_LOGIC_MODULES:
        for mod in _imported_modules(ROOT / rel):
            if mod in stdlib_ok or mod in own_package_modules:
                continue
            unexpected.setdefault(rel, set()).add(mod)

    assert not unexpected, f"逻辑层引入了非标准库依赖：{unexpected}"
