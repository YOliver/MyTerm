from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QInputMethodEvent
from PySide6.QtCore import Qt, QTimer, QEvent, QRectF
from pyte.screens import HistoryScreen
import pyte
import wcwidth

from store.clipboard_image import format_path_for_pty, save_clipboard_image
from store.paths import cache_dir


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


def cell_width(ch: str) -> int:
    """返回字符在终端里实际占的列数。空字符串/None 视为 1 格占位。

    歧义宽字符（_EAST_ASIAN_AMBIGUOUS_WIDE）在 CJK 环境下按 2 格处理，
    其余依赖 wcwidth.wcwidth；wcwidth 返回 -1/0 的（控制字符等）夹到 1。
    """
    if not ch:
        return 1
    first = ch[0]
    if first in _EAST_ASIAN_AMBIGUOUS_WIDE:
        return 2
    w = wcwidth.wcwidth(first)
    return max(w, 1)


class TerminalWidget(QWidget):
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start(200)

    def _on_data(self, data):
        self._stream.feed(data)
        self._scroll_offset = 0
        self._sel_start = None
        self._sel_end = None
        self.update()

    def _on_exit(self, exit_code):
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
                if char and char.data and char.data != " ":
                    w = cell_width(char.data)
                    px_width = self._char_width * w
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg_check = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                        bg = fg_check
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR
                    painter.fillRect(x, y, px_width, self._char_height, bg)
                    col += w
                else:
                    bg = SEL_COLOR if self._in_selection(idx, col) else DEFAULT_BG
                    painter.fillRect(x, y, self._char_width, self._char_height, bg)
                    col += 1

        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                if char and char.data and char.data != " ":
                    w = cell_width(char.data)
                    px_width = self._char_width * w
                    fg = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg, bg = bg, fg
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR

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
                else:
                    col += 1

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
        new_offset = clamp_scroll_offset(self._scroll_offset - lines, history_len)
        if new_offset != self._scroll_offset:
            self._scroll_offset = new_offset
            self.update()

    def _scroll_to_top(self) -> None:
        history_len = len(self._screen.history.top)
        if self._scroll_offset != history_len:
            self._scroll_offset = history_len
            self.update()

    def _scroll_to_bottom(self) -> None:
        if self._scroll_offset != 0:
            self._scroll_offset = 0
            self.update()

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
        if seq is not None:
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # 有真实选区：粘选区，不走剪贴板；否则回退到剪贴板（行为类似 Windows Terminal）
            if self._has_real_selection():
                text = self._get_selected_text()
                if text:
                    self._backend.write(text)
                self._sel_start = None
                self._sel_end = None
                self.update()
            else:
                # 顺手把可能存在的"假选区"（左键单击残留）清掉，避免后续渲染异常
                if self._sel_start is not None:
                    self._sel_start = None
                    self._sel_end = None
                    self.update()
                self._paste_from_clipboard()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._sel_start = self._pos_to_cell(event.pos())
            self._sel_end = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._sel_start is not None:
            self._sel_end = self._pos_to_cell(event.pos())
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._sel_start is not None:
            if self._sel_end is None:
                self._sel_end = self._sel_start
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
        self._sel_start = None
        self._sel_end = None
        self.update()

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
                    self._backend.write(format_path_for_pty(path))
                    return
        text = clipboard.text()
        if text:
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
