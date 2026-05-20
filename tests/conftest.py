"""pytest 共享 fixture。

仅在确实需要构造 QWidget 时才提供 QApplication。绝大多数测试都是
纯逻辑模块级，不依赖 Qt 应用实例 —— 沿用工程历来约定。
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def qapp():
    """会话级共享 QApplication。

    Qt 进程内只能有一个 QApplication 实例，所以做成 session 级。
    用 offscreen 平台插件，避免 CI / headless 环境下需要真显示器。
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # 不调用 app.quit()：session 结束 Python 退出会自然清理；
    # 主动 quit 反而可能让其它 fixture 在销毁时拿不到事件循环。
