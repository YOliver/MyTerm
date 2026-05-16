from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QInputMethodEvent
from PySide6.QtCore import Qt, QTimer, QEvent
from pyte.screens import HistoryScreen
import pyte
import wcwidth


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


class TerminalWidget(QWidget):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._screen = HistoryScreen(80, 24, history=2000)
        self._stream = pyte.Stream(self._screen)
        self._font = QFont("Consolas", 14)
        self._fm = QFontMetrics(self._font)
        self._char_width = self._fm.horizontalAdvance("A")
        self._char_height = self._fm.height()
        self._cursor_visible = True
        self._scroll_offset = 0
        self._sel_start = None    # (abs_row, col)
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
        self.update()

    def _in_selection(self, abs_row, col):
        """Check if cell (abs_row, col) is within the current selection."""
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

        # Collect visible rows
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

        # Pass 1: fill all backgrounds
        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                if char and char.data and char.data != " ":
                    w = wcwidth.wcwidth(char.data[0])
                    cell_width = self._char_width * max(w, 1)
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg_check = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                        bg = fg_check
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR
                    painter.fillRect(x, y, cell_width, self._char_height, bg)
                    col += max(w, 1)
                else:
                    bg = SEL_COLOR if self._in_selection(idx, col) else DEFAULT_BG
                    painter.fillRect(x, y, self._char_width, self._char_height, bg)
                    col += 1

        # Pass 2: draw all text + underlines
        for idx, y, line in rows:
            col = 0
            while col < self._screen.columns:
                x = col * self._char_width
                if x > self.width():
                    break
                char = line.get(col)
                if char and char.data and char.data != " ":
                    w = wcwidth.wcwidth(char.data[0])
                    cell_width = self._char_width * max(w, 1)
                    fg = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG
                    if char.reverse:
                        fg, bg = bg, fg
                    if self._in_selection(idx, col):
                        bg = SEL_COLOR

                    painter.setPen(fg)
                    if char.bold or char.italics:
                        f = QFont(self._font)
                        if char.bold:
                            f.setBold(True)
                        if char.italics:
                            f.setItalic(True)
                        painter.setFont(f)
                    painter.drawText(x, y + self._fm.ascent(), char.data)
                    if char.bold or char.italics:
                        painter.setFont(self._font)
                    if char.underscore:
                        painter.drawLine(x, y + self._char_height - 1,
                                         x + cell_width, y + self._char_height - 1)
                    col += max(w, 1)
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
        history_len = len(self._screen.history.top)
        max_offset = max(0, history_len)
        if delta > 0:
            self._scroll_offset = max(0, self._scroll_offset - lines)
        else:
            self._scroll_offset = min(max_offset, self._scroll_offset + lines)
        self.update()

    def _to_qcolor(self, color_str):
        if color_str in NAMED_COLORS:
            return NAMED_COLORS[color_str]
        if len(color_str) == 6:
            try:
                r = int(color_str[0:2], 16)
                g = int(color_str[2:4], 16)
                b = int(color_str[4:6], 16)
                return QColor(r, g, b)
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
            from PySide6.QtCore import QRectF
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

        if key == Qt.Key.Key_Backspace:
            self._backend.write("\x7f")
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self._backend.write("\r")
        elif key == Qt.Key.Key_Tab:
            self._backend.write("\t")
        elif key == Qt.Key.Key_Escape:
            self._backend.write("\x1b")
        elif key == Qt.Key.Key_Up:
            self._backend.write("\x1b[A")
        elif key == Qt.Key.Key_Down:
            self._backend.write("\x1b[B")
        elif key == Qt.Key.Key_Right:
            self._backend.write("\x1b[C")
        elif key == Qt.Key.Key_Left:
            self._backend.write("\x1b[D")
        elif key == Qt.Key.Key_Home:
            self._backend.write("\x1b[H")
        elif key == Qt.Key.Key_End:
            self._backend.write("\x1b[F")
        elif key == Qt.Key.Key_Delete:
            self._backend.write("\x1b[3~")
        elif key == Qt.Key.Key_PageUp:
            self._backend.write("\x1b[5~")
        elif key == Qt.Key.Key_PageDown:
            self._backend.write("\x1b[6~")
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            if modifiers & Qt.KeyboardModifier.ShiftModifier:
                if key == Qt.Key.Key_C:
                    self._copy_selection()
                    return
            elif key == Qt.Key.Key_C:
                if self._sel_start is not None:
                    self._copy_selection()
                    return
                self._backend.write("\x03")
            elif key == Qt.Key.Key_D:
                self._backend.write("\x04")
            elif key == Qt.Key.Key_Z:
                self._backend.write("\x1a")
            elif key == Qt.Key.Key_V:
                clipboard = QApplication.clipboard().text()
                if clipboard:
                    self._backend.write(clipboard)
            elif key == Qt.Key.Key_A:
                self._backend.write("\x01")
            elif key == Qt.Key.Key_E:
                self._backend.write("\x05")
            elif key == Qt.Key.Key_L:
                self._backend.write("\x0c")
        elif text and len(text) > 0:
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._sel_start is not None:
                text = self._get_selected_text()
                if text:
                    self._backend.write(text)
                self._sel_start = None
                self._sel_end = None
                self.update()
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
                    w = wcwidth.wcwidth(ch.data[0])
                    col += max(w, 1)
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

    def set_font_size(self, size):
        self._font = QFont("Consolas", size)
        self._fm = QFontMetrics(self._font)
        self._char_width = self._fm.horizontalAdvance("A")
        self._char_height = self._fm.height()
        self._apply_resize()
