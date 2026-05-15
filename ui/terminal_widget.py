from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QInputMethodEvent
from PySide6.QtCore import Qt, QTimer
import pyte
import wcwidth


DEFAULT_FG = QColor(192, 192, 192)
DEFAULT_BG = QColor(12, 12, 12)
CURSOR_COLOR = QColor(255, 255, 255)

ANSI_COLORS = {
    0:  QColor(12, 12, 12),
    1:  QColor(197, 15, 31),
    2:  QColor(19, 161, 14),
    3:  QColor(193, 156, 0),
    4:  QColor(0, 55, 218),
    5:  QColor(136, 23, 152),
    6:  QColor(58, 150, 221),
    7:  QColor(204, 204, 204),
    8:  QColor(118, 118, 118),
    9:  QColor(231, 72, 86),
    10: QColor(22, 198, 12),
    11: QColor(249, 241, 165),
    12: QColor(59, 120, 255),
    13: QColor(180, 0, 158),
    14: QColor(97, 214, 214),
    15: QColor(242, 242, 242),
}


class TerminalWidget(QWidget):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._screen = pyte.Screen(80, 24)
        self._stream = pyte.Stream(self._screen)
        self._font = QFont("Consolas", 14)
        self._fm = QFontMetrics(self._font)
        self._char_width = self._fm.horizontalAdvance("A")
        self._char_height = self._fm.height()
        self._cursor_visible = True

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
        self.update()

    def _on_exit(self, exit_code):
        msg = f"\r\n\n[Process exited with code {exit_code}]\r\n"
        self._stream.feed(msg)
        self.update()

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self._font)

        for row in range(self._screen.lines):
            y = row * self._char_height
            if y > self.height():
                break

            line = self._screen.buffer.get(row, {})
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

                    painter.fillRect(x, y, cell_width, self._char_height, bg)
                    painter.setPen(fg)
                    if char.bold:
                        f = QFont(self._font)
                        f.setBold(True)
                        painter.setFont(f)
                    painter.drawText(x, y + self._fm.ascent(), char.data)
                    if char.bold:
                        painter.setFont(self._font)
                    col += max(w, 1)
                else:
                    painter.fillRect(x, y, self._char_width, self._char_height, DEFAULT_BG)
                    col += 1

        if self._cursor_visible and self._screen.cursor.hidden == False:
            cx = self._screen.cursor.x * self._char_width
            cy = self._screen.cursor.y * self._char_height
            painter.fillRect(cx, cy, self._char_width, self._char_height, CURSOR_COLOR)

        painter.end()

    def _to_qcolor(self, color_str):
        if color_str in ANSI_COLORS:
            return ANSI_COLORS[color_str]
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
            if key == Qt.Key.Key_C:
                self._backend.write("\x03")
            elif key == Qt.Key.Key_D:
                self._backend.write("\x04")
            elif key == Qt.Key.Key_Z:
                self._backend.write("\x1a")
            elif key == Qt.Key.Key_V:
                if text:
                    self._backend.write(text)
            elif key == Qt.Key.Key_A:
                self._backend.write("\x01")
            elif key == Qt.Key.Key_E:
                self._backend.write("\x05")
            elif key == Qt.Key.Key_L:
                self._backend.write("\x0c")
        elif text and len(text) > 0:
            self._backend.write(text)

    def set_font_size(self, size):
        self._font = QFont("Consolas", size)
        self._fm = QFontMetrics(self._font)
        self._char_width = self._fm.horizontalAdvance("A")
        self._char_height = self._fm.height()
        self._apply_resize()
