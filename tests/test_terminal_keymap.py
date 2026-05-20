"""键盘控制字节映射 + keyPressEvent 路由测试。

行编辑快捷键（Ctrl+W/U/K/Backspace 等）必须透传给 PTY，由 shell 自己决定
删多少 —— MyTerm 不掌握 shell 的输入缓冲，不能自己算字符数。

字典层只断 _ctrlmap 内容；路由层用 fake backend 注入 TerminalWidget，
直接调 keyPressEvent 验证 backend.write 收到了什么字节。
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent

from ui.terminal_widget import TerminalWidget


# ----------------------------- 字典层 -----------------------------

def test_ctrlmap_existing_bindings_unchanged():
    """已有的 5 个 Ctrl 绑定不能因新加映射被改坏。"""
    cm = TerminalWidget._ctrlmap
    assert cm[Qt.Key.Key_D] == "\x04"  # EOF
    assert cm[Qt.Key.Key_Z] == "\x1a"  # Suspend
    assert cm[Qt.Key.Key_A] == "\x01"  # 行首
    assert cm[Qt.Key.Key_E] == "\x05"  # 行尾
    assert cm[Qt.Key.Key_L] == "\x0c"  # 清屏


def test_ctrlmap_line_editing_added():
    """新增的行编辑快捷键映射到终端约定的控制字节。"""
    cm = TerminalWidget._ctrlmap
    assert cm[Qt.Key.Key_W] == "\x17"          # Ctrl+W           删词
    assert cm[Qt.Key.Key_U] == "\x15"          # Ctrl+U           删到行首
    assert cm[Qt.Key.Key_K] == "\x0b"          # Ctrl+K           删到行尾
    assert cm[Qt.Key.Key_Backspace] == "\x17"  # Ctrl+Backspace   等同 Ctrl+W


def test_plain_backspace_keymap_unchanged():
    """普通 Backspace 仍是 DEL（\\x7f）；只有按住 Ctrl 时才走 \\x17。"""
    assert TerminalWidget._keymap[Qt.Key.Key_Backspace] == "\x7f"


# ----------------------------- 路由层 -----------------------------

class _FakeBackend(QObject):
    """收集 write 调用，用来验证 keyPressEvent 派发到哪条字节。

    继承 QObject 并暴露 data_received / process_exited 信号，
    满足 TerminalWidget.__init__ 里的 connect 调用。
    """

    data_received = Signal(str)
    process_exited = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def write(self, data: str) -> None:
        self.writes.append(data)


@pytest.fixture
def widget(qapp):
    """构造 TerminalWidget；qapp 来自 conftest，session 级共享。"""
    backend = _FakeBackend()
    w = TerminalWidget(backend)
    return w, backend


def _press(widget: TerminalWidget, key: Qt.Key, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier, text: str = "") -> None:
    """合成一次按键事件并派发给 widget.keyPressEvent。"""
    ev = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
    widget.keyPressEvent(ev)


def test_plain_backspace_sends_del(widget):
    """普通 Backspace → \\x7f。"""
    w, backend = widget
    _press(w, Qt.Key.Key_Backspace)
    assert backend.writes == ["\x7f"]


def test_ctrl_backspace_sends_etb(widget):
    """Ctrl+Backspace → \\x17（关键回归点：以前会被 _keymap 抢走变成 \\x7f）。"""
    w, backend = widget
    _press(w, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)
    assert backend.writes == ["\x17"]


def test_ctrl_w_sends_etb(widget):
    """Ctrl+W → \\x17（删词）。"""
    w, backend = widget
    _press(w, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    assert backend.writes == ["\x17"]


def test_ctrl_u_sends_nak(widget):
    """Ctrl+U → \\x15（删到行首）。"""
    w, backend = widget
    _press(w, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier)
    assert backend.writes == ["\x15"]


def test_ctrl_k_sends_vt(widget):
    """Ctrl+K → \\x0b（删到行尾）。"""
    w, backend = widget
    _press(w, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    assert backend.writes == ["\x0b"]


def test_existing_ctrl_a_still_works(widget):
    """回归：原有 Ctrl+A → \\x01（行首）不受新映射影响。"""
    w, backend = widget
    _press(w, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert backend.writes == ["\x01"]


def test_plain_arrow_still_routed_via_keymap(widget):
    """回归：方向键这类没有 Ctrl 修饰符的按键继续走 _keymap。"""
    w, backend = widget
    _press(w, Qt.Key.Key_Left)
    assert backend.writes == ["\x1b[D"]


def test_plain_enter_still_works(widget):
    """回归：回车依然 → \\r。"""
    w, backend = widget
    _press(w, Qt.Key.Key_Return)
    assert backend.writes == ["\r"]
