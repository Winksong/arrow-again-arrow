"""骨架自检：确认包结构与依赖在干净环境下可用。

这一条测试从第一天就存在，用来保证「别人克隆下来能跑」。
"""

from __future__ import annotations


def test_package_importable():
    import game

    assert game.__version__


def test_pygame_available():
    import pygame

    assert pygame.version.ver


def test_main_entry_callable():
    import main

    assert callable(main.main)
