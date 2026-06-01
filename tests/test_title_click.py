"""终端标题按钮点击测试：点击后应调用 os.startfile 打开对应目录。"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from ui.main_window import MainWindow


@pytest.fixture
def main_window(qapp):
    """构造 MainWindow 实例（不启动终端）。"""
    with patch("ui.main_window.TerminalBackend"):
        win = MainWindow()
        yield win
        win.close()


def test_title_click_opens_explorer(main_window):
    """点击标题按钮后，os.startfile 被调用且参数为对应路径。"""
    path = r"C:\Users\test\项目A"
    dummy_terminal = QWidget()
    tile = main_window._make_tile(path, dummy_terminal, slot_idx=0, shell_label="bash")

    buttons = tile.findChildren(QPushButton)
    title_btn = next(b for b in buttons if "项目A" in b.text())

    with patch("os.startfile") as mock_open:
        title_btn.click()
        mock_open.assert_called_once_with(path)
