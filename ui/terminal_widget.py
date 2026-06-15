import logging
from functools import lru_cache

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QInputMethodEvent
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF, Signal
from pyte.screens import HistoryScreen
import pyte
import weakref
import wcwidth

from store.clipboard_image import format_path_for_pty, save_clipboard_image
from store.paths import cache_dir

logger = logging.getLogger(__name__)


# 图片粘贴缓存目录：开发态 .paste_cache/，打包态 %LOCALAPPDATA%/MyTerm/Cache/paste/
_PASTE_CACHE_DIR = str(cache_dir("paste"))


DEFAULT_FG = QColor(192, 192, 192)
DEFAULT_BG = QColor(12, 12, 12)
CURSOR_COLOR = QColor(255, 255, 255)
SEL_COLOR = QColor(38, 79, 120)

NAMED_COLORS = {
    "black":   QColor(12, 12, 12),
    "red":     QColor(197, 15, 31),
    "green":   QColor(19, 161, 14),
    "brown":   QColor(193, 156, 0),
    "blue":    QColor(0, 55, 218),
    "magenta": QColor(136, 23, 152),
    "cyan":    QColor(58, 150, 221),
    "white":   QColor(204, 204, 204),
    "brightblack":   QColor(118, 118, 118),
    "brightred":     QColor(231, 72, 86),
    "brightgreen":   QColor(22, 198, 12),
    "brightbrown":   QColor(249, 241, 165),
    "brightblue":    QColor(59, 120, 255),
    "brightmagenta": QColor(180, 0, 158),
    "brightcyan":    QColor(97, 214, 214),
    "brightwhite":   QColor(242, 242, 242),
    # pyte has a typo in BG_AIXTERM[105]
    "bfightmagenta": QColor(180, 0, 158),
}


def clamp_scroll_offset(offset: int, history_len: int) -> int:
    """把滚动偏移量夹到 [0, history_len] 区间。0=最新，history_len=最早。"""
    if offset < 0:
        return 0
    if offset > history_len:
        return history_len
    return offset


def follow_scroll_offset_after_feed(
    prev_offset: int,
    prev_history_len: int,
    new_history_len: int,
) -> int:
    """新输出 feed 完后该把 _scroll_offset 调到哪里。

    规则：
    - prev_offset == 0：用户原本就在底部跟随，继续保持在底部（返回 0）。
    - prev_offset > 0：用户已上滑查看历史，应保持视野静止——
      把 history 因为新输出而新增的行数补偿到 offset 上。
      history 触顶溢出（最旧的行被 deque 挤掉）时，溢出的那部分历史
      已不存在，无法再补偿，视图会自然向下漂一点；这是 ring buffer
      的固有限制，clamp 到合法区间即可。
    """
    if prev_offset <= 0:
        return 0
    grew = new_history_len - prev_history_len
    if grew < 0:
        grew = 0
    return clamp_scroll_offset(prev_offset + grew, new_history_len)


def scroll_offset_to_slider_value(scroll_offset: int, history_len: int) -> int:
    """把 _scroll_offset 转成 QScrollBar 的 value。

    QScrollBar 习惯：value=最大 → 滑块在底（看最新）；value=0 → 滑块在顶（看最旧）。
    项目内部 _scroll_offset：0=最新，history_len=最旧（与 QScrollBar 反向）。
    所以 slider_value = history_len - scroll_offset。
    """
    return clamp_scroll_offset(history_len - scroll_offset, history_len)


def slider_value_to_scroll_offset(slider_value: int, history_len: int) -> int:
    """把 QScrollBar 的 value 反向转回 _scroll_offset。和上面对称。"""
    return clamp_scroll_offset(history_len - slider_value, history_len)


def is_real_selection(
    sel_start: tuple[int, int] | None,
    sel_end: tuple[int, int] | None,
) -> bool:
    """判定是否拖出了一段非空选区。

    左键单击会把 `_sel_start` 设成点击位置但 `_sel_end` 仍是 None,
    这种情况不算选区——否则右键会被"假选区"吃掉一次，表现为右键
    两次才能粘贴。两端都存在且不相同才是真选区。
    """
    if sel_start is None or sel_end is None:
        return False
    return sel_start != sel_end


# 在中文/CJK 环境下被真终端按 2 格宽渲染、但 wcwidth.wcwidth 返回 1 的"歧义宽度"符号。
# Unicode 把这些符号定为 East Asian Ambiguous，CJK locale 下应取 2，否则取 1。
# CLI 工具（claude/codebuddy/各种状态行）用它们做图标，按 1 格算会和后续文字重叠。
# 集合按需扩充，遇到新的对齐错位再加。
_EAST_ASIAN_AMBIGUOUS_WIDE = frozenset(
    "⚠✓✗●○◎★☆■□▲△▼▽◆◇◯※→←↑↓⇒⇐⇑⇓"
)


@lru_cache(maxsize=4096)
def _char_width_cached(ch: str) -> int:
    """缓存单个字符的宽度计算，避免对相同字符重复调用 wcwidth.wcwidth。"""
    if ch in _EAST_ASIAN_AMBIGUOUS_WIDE:
        return 2
    w = wcwidth.wcwidth(ch)
    return max(w, 1)


def cell_width(ch: str) -> int:
    """返回字符在终端里实际占的列数。空字符串/None 视为 1 格占位。

    歧义宽字符（_EAST_ASIAN_AMBIGUOUS_WIDE）在 CJK 环境下按 2 格处理，
    其余委托 _char_width_cached 缓存结果，避免重复计算。
    """
    if not ch:
        return 1
    return _char_width_cached(ch[0])


class TerminalWidget(QWidget):
    # 滚动状态变化时通知外部（用来同步右侧 QScrollBar）。
    # 任何会动到 _scroll_offset 或 history_len 的路径（_on_data / _scroll_by /
    # _scroll_to_top / _scroll_to_bottom / set_scroll_offset / resize 后的 update）
    # 都要 emit 一下；外部根据三元组重建滚动条 range/value/page_step。
    scroll_state_changed = Signal()

    # 跨实例「当前选区持有者」弱引用：
    # 用户在 A 终端拖出选区、再到 B 终端右键时，B 需要拿到 A 的选区文本来复制。
    # 用 weakref 不阻止 widget 析构；多实例时只跟踪「最近一次产生选区」的那个,
    # 与 Windows Terminal 的「最后一次选区」语义一致。任何路径清空选区时都要
    # 把这里同步清掉，避免引用悬空。
    _selection_owner: "weakref.ReferenceType[TerminalWidget] | None" = None

    _keymap = {
        Qt.Key.Key_Backspace: "\x7f",
        Qt.Key.Key_Return: "\r", Qt.Key.Key_Enter: "\r",
        Qt.Key.Key_Tab: "\t", Qt.Key.Key_Escape: "\x1b",
        Qt.Key.Key_Up: "\x1b[A", Qt.Key.Key_Down: "\x1b[B",
        Qt.Key.Key_Right: "\x1b[C", Qt.Key.Key_Left: "\x1b[D",
        Qt.Key.Key_Home: "\x1b[H", Qt.Key.Key_End: "\x1b[F",
        Qt.Key.Key_Delete: "\x1b[3~",
        Qt.Key.Key_PageUp: "\x1b[5~", Qt.Key.Key_PageDown: "\x1b[6~",
    }
    _ctrlmap = {
        Qt.Key.Key_D: "\x04", Qt.Key.Key_Z: "\x1a",
        Qt.Key.Key_A: "\x01", Qt.Key.Key_E: "\x05", Qt.Key.Key_L: "\x0c",
        # 行编辑：让 shell（PSReadLine / bash readline 等）按各自约定处理。
        # MyTerm 不知道当前提示符里有几个字，只能透传控制字节，删多少由 shell 决定。
        Qt.Key.Key_W: "\x17",          # Ctrl+W           删除光标前一个单词
        Qt.Key.Key_U: "\x15",          # Ctrl+U           删除从光标到行首
        Qt.Key.Key_K: "\x0b",          # Ctrl+K           删除从光标到行尾
        Qt.Key.Key_Backspace: "\x17",  # Ctrl+Backspace   Windows 习惯，等同 Ctrl+W
    }

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._screen = HistoryScreen(80, 24, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._font = QFont("Consolas", 14)
        self._build_font_variants()
        self._update_font_metrics()
        self._cursor_visible = True
        self._scroll_offset = 0
        self._sel_start = None
        self._sel_end = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setMinimumSize(400, 200)
        self.setAutoFillBackground(True)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_resize)

        backend.data_received.connect(self._on_data)
        backend.process_exited.connect(self._on_exit)

        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(530)

    def _apply_resize(self):
        cols = max(10, self.width() // self._char_width)
        rows = max(5, self.height() // self._char_height)
        self._screen.resize(rows, cols)
        self._backend.resize(cols, rows)
        self.update()
        # 行数变化会改变 page_step（滚动条滑块大小），通知外部重算
        self.scroll_state_changed.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(200)

    def _on_data(self, data):
        # 用户上滑查看历史（_scroll_offset > 0）时不应被新输出弹回底部，
        # 否则 tail -f / build 输出狂刷时根本没法看历史。
        # 只有原本就贴在底部（offset == 0）才跟随；否则按 history 增长量
        # 补偿 offset 让视野静止。
        prev_offset = self._scroll_offset
        prev_history_len = len(self._screen.history.top)
        self._stream.feed(data)
        new_history_len = len(self._screen.history.top)
        self._scroll_offset = follow_scroll_offset_after_feed(
            prev_offset, prev_history_len, new_history_len,
        )
        # 收到 PTY 新输出会让选区坐标失效（屏幕滚动 / 内容覆盖），统一清掉。
        # 走 _clear_selection 是为了同时解除全局 _selection_owner 引用，
        # 否则其它终端右键时还能"复制"到一段早已不存在的内容。
        self._clear_selection(repaint=False)
        self.update()
        # history 几乎每次都在变（即便 offset 没动），滚动条的 range/value
        # 都需要重算，所以无条件通知。
        self.scroll_state_changed.emit()

    def _on_exit(self, exit_code):
        logger.info("TerminalWidget 收到进程退出信号: exit_code=%d, widget=%s",
                     exit_code, id(self))
        msg = f"\r\n\n[Process exited with code {exit_code}]\r\n"
        self._stream.feed(msg)
        self.update()

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        cx = self._screen.cursor.x * self._char_width
        cy = self._screen.cursor.y * self._char_height
        self.update(cx, cy, self._char_width, self._char_height)

    def _build_font_variants(self):
        self._font_bold = QFont(self._font)
        self._font_bold.setBold(True)
        self._font_italic = QFont(self._font)
        self._font_italic.setItalic(True)
        self._font_bi = QFont(self._font)
        self._font_bi.setBold(True)
        self._font_bi.setItalic(True)

    def _update_font_metrics(self):
        self._fm = QFontMetrics(self._font)
        self._char_width = self._fm.horizontalAdvance("A")
        self._char_height = self._fm.height()

    def _in_selection(self, abs_row, col):
        sel_start, sel_end = self._normalize_selection()
        if sel_start is None:
            return False
        sr, sc = sel_start
        er, ec = sel_end
        if abs_row < sr or abs_row > er:
            return False
        if abs_row == sr and col < sc:
            return False
        if abs_row == er and col >= ec:
            return False
        return True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        painter.setFont(self._font)

        history = self._screen.history.top
        history_len = len(history)
        visible_rows = self._screen.lines
        total = history_len + visible_rows

        max_offset = max(0, total - visible_rows)
        if self._scroll_offset > max_offset:
            self._scroll_offset = max_offset

        start = max(0, total - visible_rows - self._scroll_offset)
        end = total - self._scroll_offset

        rows = []
        for idx in range(start, end):
            screen_row = idx - start
            y = screen_row * self._char_height
            if y > self.height():
                break
            if idx < history_len:
                line = history[idx]
            else:
                line = self._screen.buffer.get(idx - history_len, {})
            rows.append((idx, y, line))

        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                has_real_char = bool(char and char.data and char.data != " ")
                is_reverse_space = bool(char and char.reverse and not has_real_char)

                # ---- 背景 ----
                if has_real_char or is_reverse_space:
                    w = cell_width(char.data) if has_real_char else 1
                    px_width = self._char_width * w
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg_check = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                        bg = fg_check
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR
                    painter.fillRect(x, y, px_width, self._char_height, bg)
                else:
                    w = 1
                    px_width = self._char_width
                    bg = SEL_COLOR if self._in_selection(idx, col) else DEFAULT_BG
                    painter.fillRect(x, y, px_width, self._char_height, bg)

                # ---- 前景文字 ----
                if has_real_char:
                    fg = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                    bg_for_fg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg, bg_for_fg = bg_for_fg, fg
                    # 注意：原版第二遍里 selection 只改 bg（死代码），不改 fg，
                    # 所以选中区文字色保持原 fg（或 reverse 后的 fg），与背景独立。
                    painter.setPen(fg)
                    if char.bold and char.italics:
                        painter.setFont(self._font_bi)
                    elif char.bold:
                        painter.setFont(self._font_bold)
                    elif char.italics:
                        painter.setFont(self._font_italic)
                    painter.drawText(x, y + self._fm.ascent(), char.data)
                    if char.bold or char.italics:
                        painter.setFont(self._font)
                    if char.underscore:
                        painter.drawLine(x, y + self._char_height - 1,
                                         x + px_width, y + self._char_height - 1)

                col += w

        if self._cursor_visible and self._scroll_offset == 0 and not self._screen.cursor.hidden:
            cx = self._screen.cursor.x * self._char_width
            cy = self._screen.cursor.y * self._char_height
            painter.fillRect(cx, cy, self._char_width, self._char_height, CURSOR_COLOR)

        painter.end()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        lines = max(1, abs(delta) // 120)
        self._scroll_by(-lines if delta > 0 else lines)

    def _visible_rows(self) -> int:
        return max(1, self._screen.lines)

    def _scroll_by(self, lines: int) -> None:
        """正数减小 offset（看更新），负数增大 offset（看更旧）。语义与 wheelEvent 一致。"""
        history_len = len(self._screen.history.top)
        old_offset = self._scroll_offset
        new_offset = clamp_scroll_offset(old_offset - lines, history_len)
        if new_offset != old_offset:
            self._scroll_offset = new_offset
            logger.debug("滚动: offset %d -> %d (lines=%d)", old_offset, new_offset, lines)
            self.update()
            self.scroll_state_changed.emit()

    def _scroll_to_top(self) -> None:
        history_len = len(self._screen.history.top)
        if self._scroll_offset != history_len:
            logger.debug("滚动到顶部: offset %d -> %d", self._scroll_offset, history_len)
            self._scroll_offset = history_len
            self.update()
            self.scroll_state_changed.emit()

    def _scroll_to_bottom(self) -> None:
        if self._scroll_offset != 0:
            logger.debug("滚动到底部: offset %d -> 0", self._scroll_offset)
            self._scroll_offset = 0
            self.update()
            self.scroll_state_changed.emit()

    def set_scroll_offset(self, offset: int) -> None:
        """外部（右侧 QScrollBar 拖动）设置滚动偏移；做 clamp 后回写。"""
        history_len = len(self._screen.history.top)
        new_offset = clamp_scroll_offset(offset, history_len)
        if new_offset != self._scroll_offset:
            self._scroll_offset = new_offset
            self.update()
            # 注意：这里**不**再 emit scroll_state_changed —— 调用方就是滚动条本身,
            # 让滚动条响应自己 emit 的信号会引起反向同步循环。

    def get_scroll_state(self) -> tuple[int, int, int]:
        """返回 (scroll_offset, history_len, visible_rows) 三元组，给外部刷新滚动条用。"""
        return self._scroll_offset, len(self._screen.history.top), self._screen.lines

    def _to_qcolor(self, color_str):
        if color_str in NAMED_COLORS:
            return NAMED_COLORS[color_str]
        if len(color_str) == 6:
            try:
                v = int(color_str, 16)
                return QColor((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
            except ValueError:
                pass
        return DEFAULT_FG

    def inputMethodEvent(self, event):
        commit = event.commitString()
        if commit:
            self._backend.write(commit)

    def inputMethodQuery(self, query):
        if query == Qt.InputMethodQuery.ImCursorRectangle:
            cx = self._screen.cursor.x * self._char_width
            cy = self._screen.cursor.y * self._char_height
            return QRectF(cx, cy, self._char_width, self._char_height)
        return None

    def event(self, event):
        if event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        text = event.text()
        key = event.key()
        modifiers = event.modifiers()

        # Shift + Page/Home/End：滚动历史（必须在 _keymap 之前拦截，
        # 否则 PageUp/PageDown 会被转发给 PTY 用于 vim/less）
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_PageUp:
                self._scroll_by(-(max(1, self._visible_rows() - 1)))
                return
            if key == Qt.Key.Key_PageDown:
                self._scroll_by(max(1, self._visible_rows() - 1))
                return
            if key == Qt.Key.Key_Home:
                self._scroll_to_top()
                return
            if key == Qt.Key.Key_End:
                self._scroll_to_bottom()
                return

        seq = self._keymap.get(key)
        if seq is not None and not (modifiers & Qt.KeyboardModifier.ControlModifier):
            # 仅在没按 Ctrl 时走 _keymap：否则 Ctrl+Backspace 这类组合会被
            # _keymap[Backspace]=\x7f 抢走，永远进不到下面 Ctrl 分支里的 _ctrlmap。
            self._backend.write(seq)
            return

        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if modifiers & Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_C:
                self._copy_selection()
                return
            if key == Qt.Key.Key_C:
                if self._sel_start is not None:
                    self._copy_selection()
                    return
                self._backend.write("\x03")
                return
            cseq = self._ctrlmap.get(key)
            if cseq is not None:
                self._backend.write(cseq)
                return
            if key == Qt.Key.Key_V:
                self._paste_from_clipboard()
                return

        # Ctrl 分支没消化掉的非字符键（比如 Ctrl+方向键）回退到 _keymap，避免被吞
        if seq is not None:
            self._backend.write(seq)
            return

        if text:
            self._backend.write(text)

    def _abs_row(self):
        """First visible absolute row index."""
        history_len = len(self._screen.history.top)
        visible_rows = self._screen.lines
        total = history_len + visible_rows
        return max(0, total - visible_rows - self._scroll_offset)

    def _pos_to_cell(self, pos):
        """Convert mouse position to (abs_row, col)."""
        abs_row = self._abs_row() + pos.y() // self._char_height
        col = pos.x() // self._char_width
        return abs_row, col

    def _has_real_selection(self) -> bool:
        """实例侧的便捷封装，逻辑见模块级 `is_real_selection`。"""
        return is_real_selection(self._sel_start, self._sel_end)

    def _set_selection_owner(self) -> None:
        """声明"我现在持有选区"。供跨实例右键复制时反查文本来源。"""
        TerminalWidget._selection_owner = weakref.ref(self)

    def _clear_selection(self, repaint: bool = True) -> None:
        """统一的"清掉本实例选区"入口：清状态 + 解除全局所有权 + 可选重绘。

        多个清空路径（_on_data / _copy_selection / 右键消化掉选区 / mousePressEvent
        擦假选区）都走这里，避免某条分支忘了把 _selection_owner 复位。
        """
        had = self._sel_start is not None or self._sel_end is not None
        self._sel_start = None
        self._sel_end = None
        owner = TerminalWidget._selection_owner
        if owner is not None and owner() is self:
            TerminalWidget._selection_owner = None
        if repaint and had:
            self.update()

    @classmethod
    def _peek_other_selection_text(cls, exclude: "TerminalWidget") -> str:
        """若有另一个 TerminalWidget 当前持有选区，返回其文本；否则空串。

        ``exclude`` 是发起方（右键被点的 widget），它自己有选区时由调用方先处理，
        这里专门处理"别的实例持有选区"的跨终端场景。
        """
        owner_ref = cls._selection_owner
        if owner_ref is None:
            return ""
        owner = owner_ref()
        if owner is None or owner is exclude:
            return ""
        if not owner._has_real_selection():
            return ""
        return owner._get_selected_text()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # 优先级：本实例选区 > 其它终端实例选区 > 剪贴板。
            # 跨终端的"在 A 选 → 在 B 右键"场景靠 _selection_owner 全局引用支持，
            # 行为对齐 Windows Terminal：右键既能粘贴也能"把上一段选区发到这里"。
            if self._has_real_selection():
                text = self._get_selected_text()
                if text:
                    self._backend.write(text)
                self._clear_selection()
                return
            cross_text = TerminalWidget._peek_other_selection_text(exclude=self)
            if cross_text:
                self._backend.write(cross_text)
                # 消化掉源端的选区：与同终端右键一致的语义（选完一次就用掉）
                owner_ref = TerminalWidget._selection_owner
                owner = owner_ref() if owner_ref is not None else None
                if owner is not None:
                    owner._clear_selection()
                return
            # 顺手把可能存在的"假选区"（左键单击残留）清掉，避免后续渲染异常
            if self._sel_start is not None:
                self._clear_selection()
            self._paste_from_clipboard()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # 切换选区源：原来的持有者（可能是别的终端）让位给当前实例。
            # 同实例情况下 _set_selection_owner 仍要在 mouseMove/release 后调；
            # 这里只做"开始一次新拖动"的状态重置。
            self._sel_start = self._pos_to_cell(event.pos())
            self._sel_end = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._sel_start is not None:
            self._sel_end = self._pos_to_cell(event.pos())
            if self._has_real_selection():
                # 拖出真实范围才声明"我是选区源"，避免误把单击残留登记为源
                self._set_selection_owner()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._sel_start is not None:
            if self._sel_end is None:
                self._sel_end = self._sel_start
            if self._has_real_selection():
                self._set_selection_owner()
            self.update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            row, col = self._pos_to_cell(event.pos())
            line = self._line_at(row)
            if line:
                # Select word: find boundaries
                start_col = col
                end_col = col
                while start_col > 0:
                    ch = line.get(start_col - 1)
                    if ch and ch.data and ch.data != " ":
                        start_col -= 1
                    else:
                        break
                while True:
                    ch = line.get(end_col)
                    if ch and ch.data and ch.data != " ":
                        end_col += 1
                    else:
                        break
                self._sel_start = (row, start_col)
                self._sel_end = (row, end_col)
                if self._has_real_selection():
                    self._set_selection_owner()
                self.update()
        super().mouseDoubleClickEvent(event)

    def _line_at(self, abs_row):
        """Get the dict-like row at the given absolute row index."""
        history = self._screen.history.top
        history_len = len(history)
        if abs_row < history_len:
            return history[abs_row]
        return self._screen.buffer.get(abs_row - history_len, {})

    def _normalize_selection(self):
        """Return (start, end) ordered so start is before end."""
        if self._sel_start is None:
            return None, None
        end = self._sel_end or self._sel_start
        if self._sel_start[0] < end[0] or (
            self._sel_start[0] == end[0] and self._sel_start[1] <= end[1]
        ):
            return self._sel_start, end
        return end, self._sel_start

    def _get_selected_text(self):
        start, end = self._normalize_selection()
        if start is None:
            return ""
        lines = []
        for row in range(start[0], end[0] + 1):
            line = self._line_at(row)
            if not line:
                lines.append("")
                continue
            begin_col = start[1] if row == start[0] else 0
            finish_col = end[1] if row == end[0] else self._screen.columns
            chars = []
            col = begin_col
            while col < finish_col:
                ch = line.get(col)
                if ch and ch.data:
                    chars.append(ch.data)
                    # Skip placeholder column for wide chars
                    col += cell_width(ch.data)
                else:
                    chars.append(" ")
                    col += 1
            lines.append("".join(chars).rstrip())
        return "\r\n".join(lines)

    def _copy_selection(self):
        text = self._get_selected_text()
        if text:
            QApplication.clipboard().setText(text)
            logger.info("已复制选区到剪贴板: 长度=%d", len(text))
        self._clear_selection()

    def _paste_from_clipboard(self):
        """统一的粘贴入口：剪贴板有图就落盘并写入路径，否则回退到文本。

        QQ 截图、浏览器复制图片等场景剪贴板会同时携带图与文本两份格式，
        此处采用"图优先"——直觉上有图就是想发图（claude/codebuddy 都支持读图）。
        若落盘失败（磁盘问题等）静默回退到文本，保证粘贴动作不会"什么都没发生"。
        """
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is not None and mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                path = save_clipboard_image(image, _PASTE_CACHE_DIR)
                if path:
                    logger.info("粘贴图片: path=%s", path)
                    self._backend.write(format_path_for_pty(path))
                    return
        text = clipboard.text()
        if text:
            logger.info("粘贴文本: 长度=%d", len(text))
            self._backend.write(text)

    @property
    def columns(self):
        return self._screen.columns

    @property
    def rows(self):
        return self._screen.lines

    def set_font_size(self, size):
        self._font = QFont("Consolas", size)
        self._build_font_variants()
        self._update_font_metrics()
        self._apply_resize()
