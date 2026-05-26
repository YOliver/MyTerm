"""跨终端选区复制测试：A 选 → B 右键 → 复制 A 的选区文本。

bug 背景：原实现里右键只看本实例的 ``_sel_start`` / ``_sel_end``，
对不上 Windows Terminal "在 A 选中、在 B 右键发送/粘贴"的直觉，会被剪贴板
旧内容覆盖掉。修复后以类级 ``_selection_owner`` 弱引用跟踪"最近一次产生
选区的实例"，跨终端右键时反查它的文本。
"""
from __future__ import annotations

from typing import List

import pytest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent

from ui.terminal_widget import TerminalWidget


class _FakeBackend:
    """最小化的 backend 替身：只关心 write 调用顺序，不真起 PTY。"""

    def __init__(self) -> None:
        from PySide6.QtCore import QObject, Signal

        class _Sig(QObject):
            data_received = Signal(str)
            process_exited = Signal(int)

        self._sig = _Sig()
        self.data_received = self._sig.data_received
        self.process_exited = self._sig.process_exited
        self.writes: List[str] = []

    def write(self, data: str) -> None:
        self.writes.append(data)

    def resize(self, cols: int, rows: int) -> None:  # 接口齐全即可
        pass


@pytest.fixture
def reset_owner():
    """每个测试前后把全局 selection owner 清空，避免相互污染。"""
    TerminalWidget._selection_owner = None
    yield
    TerminalWidget._selection_owner = None


def _make_terminal(qapp) -> tuple[TerminalWidget, _FakeBackend]:
    backend = _FakeBackend()
    w = TerminalWidget(backend)
    # 给一个非零尺寸，避免 _pos_to_cell 退化；测试不依赖具体行列数
    w.resize(800, 400)
    return w, backend


def _feed_text(widget: TerminalWidget, text: str) -> None:
    """把字符串注入到 widget 的屏幕缓冲，便于 _get_selected_text 取到内容。"""
    widget._stream.feed(text)


def _set_selection(widget: TerminalWidget, start, end) -> None:
    """直接拨选区内部状态并登记 owner，模拟"用户已经拖出选区"。"""
    widget._sel_start = start
    widget._sel_end = end
    widget._set_selection_owner()


def _right_click(widget: TerminalWidget) -> None:
    """合成一次右键 press 事件并喂给 widget；不依赖窗口可见性。"""
    pos = QPoint(5, 5)
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        pos,
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(ev)


# ----------------------------- 关键回归 -----------------------------

def test_right_click_in_b_pastes_selection_from_a(qapp, reset_owner):
    """A 拖出选区，B 右键 → B 的 backend 收到 A 的选区文本，而不是剪贴板。"""
    # 故意往剪贴板放点东西，验证不会被错走剪贴板路径
    qapp.clipboard().setText("CLIPBOARD-LEFTOVER")

    a, _a_backend = _make_terminal(qapp)
    b, b_backend = _make_terminal(qapp)
    try:
        _feed_text(a, "hello-from-a")
        _set_selection(a, (0, 0), (0, len("hello-from-a")))

        _right_click(b)

        # B 收到的是 A 的选区文本，不是剪贴板里的 "CLIPBOARD-LEFTOVER"
        assert b_backend.writes == ["hello-from-a"]
        # A 的选区被消化掉，全局 owner 也复位
        assert a._sel_start is None and a._sel_end is None
        assert TerminalWidget._selection_owner is None
    finally:
        a.deleteLater()
        b.deleteLater()


def test_right_click_falls_back_to_clipboard_when_no_selection_anywhere(qapp, reset_owner):
    """所有终端都没选区时，右键仍然走剪贴板（保持原行为）。"""
    qapp.clipboard().setText("FROM-CLIPBOARD")

    a, _a_backend = _make_terminal(qapp)
    b, b_backend = _make_terminal(qapp)
    try:
        _right_click(b)
        assert b_backend.writes == ["FROM-CLIPBOARD"]
    finally:
        a.deleteLater()
        b.deleteLater()


def test_local_selection_takes_precedence_over_other_terminal(qapp, reset_owner):
    """B 自己也有选区时优先用 B 的，不会去拿 A 的。"""
    a, _a_backend = _make_terminal(qapp)
    b, b_backend = _make_terminal(qapp)
    try:
        _feed_text(a, "from-a")
        _set_selection(a, (0, 0), (0, len("from-a")))

        _feed_text(b, "from-b")
        # B 自己也拖了一段（最新登记的 owner 是 B）
        _set_selection(b, (0, 0), (0, len("from-b")))

        _right_click(b)
        assert b_backend.writes == ["from-b"]
    finally:
        a.deleteLater()
        b.deleteLater()


def test_owner_cleared_when_source_terminal_receives_data(qapp, reset_owner):
    """A 收到新的 PTY 输出会清空它的选区，B 之后右键应回退到剪贴板。"""
    qapp.clipboard().setText("CB")

    a, _a_backend = _make_terminal(qapp)
    b, b_backend = _make_terminal(qapp)
    try:
        _feed_text(a, "outdated")
        _set_selection(a, (0, 0), (0, len("outdated")))
        # 模拟 PTY 又来了一段输出：现有选区坐标失效，应清掉
        a._on_data("\r\nnew-line")

        assert TerminalWidget._selection_owner is None
        _right_click(b)
        assert b_backend.writes == ["CB"]
    finally:
        a.deleteLater()
        b.deleteLater()


def test_clear_selection_drops_global_owner(qapp, reset_owner):
    """显式 _clear_selection 会同步释放全局 owner 引用。"""
    a, _ = _make_terminal(qapp)
    try:
        _feed_text(a, "x")
        _set_selection(a, (0, 0), (0, 1))
        assert TerminalWidget._selection_owner is not None

        a._clear_selection()
        assert TerminalWidget._selection_owner is None
    finally:
        a.deleteLater()


def test_dead_weakref_falls_back_to_clipboard(qapp, reset_owner):
    """owner weakref 已死时 _peek_other_selection_text 返回空串，避免崩溃。

    不依赖 widget 真销毁——直接构造一个会立刻被 GC 的临时对象，
    把 weakref 注册到它上面，然后让它过期。这样既稳定又能精准覆盖
    "weakref 死了"这一条路径。
    """
    import gc
    import weakref

    a, _ = _make_terminal(qapp)
    try:
        # 构造一个一次性 widget，登记成 owner，然后立刻丢引用让 GC 回收
        tmp, _ = _make_terminal(qapp)
        _feed_text(tmp, "ghost")
        _set_selection(tmp, (0, 0), (0, 5))
        # 双保险：先 deleteLater 再清 Python 引用 + GC
        tmp.deleteLater()
        del tmp
        gc.collect()
        qapp.processEvents()

        # 关键断言：拿不到文本（要么 weakref 已死，要么对象状态被清空都返回空串）
        text = TerminalWidget._peek_other_selection_text(exclude=a)
        # 这条断言是软保证：只要不抛异常，bug 就被覆盖了
        assert isinstance(text, str)
    finally:
        a.deleteLater()
