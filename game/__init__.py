"""一箭又一箭 —— 游戏包。

层次划分：
    model.py   规则与数据（不依赖 pygame，可被自动化测试直接调用）
    levels.py  固定关卡数据
    solver.py  可解性校验 / 求解器
    view.py    绘制（棋盘、箭头、面板、动画）
    app.py     pygame 主循环 + 状态机 + 鼠标事件
"""

__version__ = "0.1.0"
