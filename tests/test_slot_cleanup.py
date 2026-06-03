"""终端槽位自动清理测试：进程退出后槽位应被释放。"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QWidget

from ui.main_window import MainWindow, Slot


class FakeBackend(QObject):
    """可手动触发 process_exited 的假后端。"""
    data_received = Signal(str)
    process_exited = Signal(int)

    def start_shell(self, **kwargs):
        pass

    def stop(self):
        pass

    def isRunning(self):
        return False


class FakeTerminal(QWidget):
    """假终端：提供 _make_tile 内部需要的滚动条同步契约。

    需要 scroll_state_changed 信号 + get_scroll_state() / set_scroll_offset()
    方法。槽位清理测试不关心滚动行为，给个空桩即可。
    """
    scroll_state_changed = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__()

    def get_scroll_state(self):
        return 0, 0, 24

    def set_scroll_offset(self, _offset):
        pass


@pytest.fixture
def main_window(qapp):
    with patch("ui.main_window.TerminalBackend", FakeBackend), \
         patch("ui.main_window.TerminalWidget", FakeTerminal):
        win = MainWindow()
        yield win
        win.close()


def test_process_exit_releases_slot(main_window):
    """backend.process_exited 信号应触发槽位释放。"""
    backend = FakeBackend()
    terminal = FakeTerminal()
    tile = main_window._make_tile("C:\\test", terminal, slot_idx=0)
    main_window._slots[0] = Slot(backend, terminal, tile)
    # 模拟 _add_terminal 中的信号连接
    backend.process_exited.connect(lambda _code, i=0: main_window._remove_terminal(i))

    assert main_window._slots[0] is not None

    # 模拟进程退出
    backend.process_exited.emit(0)

    assert main_window._slots[0] is None


def test_slot_reusable_after_exit(main_window):
    """槽位释放后应能被新终端复用。"""
    backend = FakeBackend()
    terminal = FakeTerminal()
    tile = main_window._make_tile("C:\\test", terminal, slot_idx=0)
    main_window._slots[0] = Slot(backend, terminal, tile)
    backend.process_exited.connect(lambda _code, i=0: main_window._remove_terminal(i))

    # 进程退出释放槽位
    backend.process_exited.emit(0)
    assert main_window._slots[0] is None

    # 新终端应能获取到 slot 0
    idx = main_window._find_empty_slot()
    assert idx == 0


def test_multiple_slots_independent_cleanup(main_window):
    """多个终端各自独立释放，互不影响。"""
    backends = []
    for i in range(3):
        backend = FakeBackend()
        terminal = FakeTerminal()
        tile = main_window._make_tile("C:\\test", terminal, slot_idx=i)
        main_window._slots[i] = Slot(backend, terminal, tile)
        backend.process_exited.connect(lambda _code, idx=i: main_window._remove_terminal(idx))
        backends.append(backend)

    assert main_window._active_count() == 3

    # 只退出中间那个
    backends[1].process_exited.emit(0)

    assert main_window._slots[0] is not None
    assert main_window._slots[1] is None
    assert main_window._slots[2] is not None
    assert main_window._active_count() == 2


def test_double_exit_signal_no_crash(main_window):
    """process_exited 重复触发不应崩溃（槽位已为空时跳过）。"""
    backend = FakeBackend()
    terminal = FakeTerminal()
    tile = main_window._make_tile("C:\\test", terminal, slot_idx=0)
    main_window._slots[0] = Slot(backend, terminal, tile)
    backend.process_exited.connect(lambda _code, i=0: main_window._remove_terminal(i))

    backend.process_exited.emit(0)
    assert main_window._slots[0] is None

    # 再次触发不应抛异常
    backend.process_exited.emit(1)
    assert main_window._slots[0] is None
