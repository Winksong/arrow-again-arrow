"""pytest 全局配置。

把无头（headless）驱动设置集中在这里，测试文件不必各自重复声明：

- ``SDL_VIDEODRIVER=dummy``：不创建真实窗口，CI 与无显示器环境可跑；
- ``SDL_AUDIODRIVER=dummy``：不初始化音频设备，避免无声卡时报错。

pytest 会在收集测试前自动导入本文件，因此这里的设置先于任何
``import pygame`` 生效。必须在导入 pygame 之前设置，否则驱动已经
被初始化，再改环境变量就不起作用了。
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
