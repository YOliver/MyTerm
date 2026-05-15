# Embedded PowerShell Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows GUI that embeds an interactive PowerShell terminal in a user-specified directory, with path history.

**Architecture:** PySide6 provides the GUI shell. pywinpty wraps Windows ConPTY to give PowerShell a true terminal environment. pyte parses ANSI escape sequences from the PTY output into a character grid that a custom QWidget renders.

**Tech Stack:** Python 3.14, PySide6 6.11, pywinpty 3.0, pyte 0.8

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Write requirements.txt**

```text
PySide6>=6.5
pywinpty>=2.0
pyte>=0.8
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add project dependencies"
```

---

### Task 2: Path history store

**Files:**
- Create: `store/__init__.py` (empty)
- Create: `store/path_history.py`
- Create: `tests/test_path_history.py`

- [ ] **Step 1: Write failing test for path_history**

```python
import pytest
from store.path_history import PathHistory

def test_add_and_get_recent():
    history = PathHistory()
    history.add("C:\\Users")
    history.add("C:\\Windows")
    
    paths = history.all()
    assert paths == ["C:\\Windows", "C:\\Users"]


def test_dedup_moves_to_top():
    history = PathHistory()
    history.add("C:\\Users")
    history.add("C:\\Windows")
    history.add("C:\\Users")
    
    paths = history.all()
    assert paths == ["C:\\Users", "C:\\Windows"]


def test_max_ten_entries():
    history = PathHistory()
    for i in range(15):
        history.add(f"C:\\path{i}")
    
    paths = history.all()
    assert len(paths) == 10
    assert paths[0] == "C:\\path14"  # most recent first


def test_empty_history_returns_empty_list():
    history = PathHistory()
    assert history.all() == []


def test_persist_and_load(tmp_path):
    history_a = PathHistory(filepath=str(tmp_path / "paths.json"))
    history_a.add("C:\\test")
    
    history_b = PathHistory(filepath=str(tmp_path / "paths.json"))
    assert history_b.all() == ["C:\\test"]
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
python -m pytest tests/test_path_history.py -v
```
Expected: all 5 tests FAIL (module not found)

- [ ] **Step 3: Implement PathHistory**

`store/path_history.py`:
```python
import json
import os


class PathHistory:
    def __init__(self, filepath=None):
        if filepath is None:
            filepath = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "path_history.json"
            )
        self._filepath = filepath
        self._paths = self._load()

    def _load(self):
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self):
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._paths, f, ensure_ascii=False)

    def add(self, path):
        path = os.path.normpath(path)
        if path in self._paths:
            self._paths.remove(path)
        self._paths.insert(0, path)
        if len(self._paths) > 10:
            self._paths = self._paths[:10]
        self._save()

    def all(self):
        return list(self._paths)
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
python -m pytest tests/test_path_history.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add store/__init__.py store/path_history.py tests/test_path_history.py
git commit -m "feat: add path history store with persist, dedup, max-10"
```

---

### Task 3: Terminal backend (pywinpty wrapper)

**Files:**
- Create: `backend/__init__.py` (empty)
- Create: `backend/terminal_backend.py`

- [ ] **Step 1: Write failing test for TerminalBackend**

No GUI test for this module -- the backend interacts with Windows ConPTY which requires a running message pump. We test it manually. Skip automated test, create the implementation directly.

- [ ] **Step 2: Implement TerminalBackend**

`backend/terminal_backend.py`:
```python
from PySide6.QtCore import QThread, Signal
from winpty import PtyProcess


class TerminalBackend(QThread):
    data_received = Signal(str)
    process_exited = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._columns = 80
        self._rows = 24

    def start_shell(self, cwd=None, columns=80, rows=24):
        self._columns = columns
        self._rows = rows
        self._process = PtyProcess.spawn(
            ["powershell.exe"],
            cwd=cwd,
            dimensions=(rows, columns),
        )
        self.start()

    def run(self):
        try:
            while self._process.isalive():
                data = self._process.read(4096, blocking=True)
                if data:
                    self.data_received.emit(data)
        except EOFError:
            pass
        finally:
            exit_code = 0
            if self._process:
                exit_code = self._process.wait()
            self.process_exited.emit(exit_code)

    def write(self, text):
        if self._process and self._process.isalive():
            self._process.write(text.encode("utf-8"))

    def resize(self, columns, rows):
        if self._process and self._process.isalive():
            self._process.setwinsize(rows, columns)

    def stop(self):
        if self._process:
            self._process.close()
        self.wait(1000)
```

- [ ] **Step 3: Quick smoke test**

```bash
python -c "from backend.terminal_backend import TerminalBackend; print('TerminalBackend OK')"
```
Expected: `TerminalBackend OK`

- [ ] **Step 4: Commit**

```bash
git add backend/__init__.py backend/terminal_backend.py
git commit -m "feat: add terminal backend wrapping pywinpty ConPTY"
```

---

### Task 4: Terminal widget (rendering + keyboard input)

**Files:**
- Create: `ui/__init__.py` (empty)
- Create: `ui/terminal_widget.py`

- [ ] **Step 1: Implement TerminalWidget**

`ui/terminal_widget.py`:
```python
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QKeyEvent
from PySide6.QtCore import Qt, QTimer
import pyte


DEFAULT_FG = QColor(192, 192, 192)
DEFAULT_BG = QColor(12, 12, 12)
CURSOR_COLOR = QColor(255, 255, 255)

# Map ANSI color indices to QColor (first 16 standard colors)
ANSI_COLORS = {
    0:  QColor(12, 12, 12),      # Black
    1:  QColor(197, 15, 31),     # Red
    2:  QColor(19, 161, 14),     # Green
    3:  QColor(193, 156, 0),     # Yellow
    4:  QColor(0, 55, 218),      # Blue
    5:  QColor(136, 23, 152),    # Magenta
    6:  QColor(58, 150, 221),    # Cyan
    7:  QColor(204, 204, 204),   # White
    8:  QColor(118, 118, 118),   # Bright Black
    9:  QColor(231, 72, 86),     # Bright Red
    10: QColor(22, 198, 12),     # Bright Green
    11: QColor(249, 241, 165),   # Bright Yellow
    12: QColor(59, 120, 255),    # Bright Blue
    13: QColor(180, 0, 158),     # Bright Magenta
    14: QColor(97, 214, 214),    # Bright Cyan
    15: QColor(242, 242, 242),   # Bright White
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
        self._needs_repaint = False

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(400, 200)
        self.setAutoFillBackground(True)

        # Recalculate terminal size on resize
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_resize)

        # Connect backend signals
        backend.data_received.connect(self._on_data)
        backend.process_exited.connect(self._on_exit)

        # Blink cursor timer
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(530)

    def _apply_resize(self):
        cols = max(10, self.width() // self._char_width)
        rows = max(5, self.height() // self._char_height)
        self._screen.resize(cols, rows)
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
            for col in range(self._screen.columns):
                x = col * self._char_width
                if x > self.width():
                    break

                char = line.get(col)
                if char:
                    fg = self._to_qcolor(char.fg) if char.fg != "default" else DEFAULT_FG
                    bg = self._to_qcolor(char.bg) if char.bg != "default" else DEFAULT_BG

                    # Draw background
                    painter.fillRect(x, y, self._char_width, self._char_height, bg)
                    # Draw text
                    painter.setPen(fg)
                    if char.bold:
                        f = QFont(self._font)
                        f.setBold(True)
                        painter.setFont(f)
                    painter.drawText(x, y + self._fm.ascent(), char.data)
                    if char.bold:
                        painter.setFont(self._font)
                else:
                    painter.fillRect(x, y, self._char_width, self._char_height, DEFAULT_BG)

        # Draw cursor
        if self._cursor_visible and self._screen.cursor.hidden == False:
            cx = self._screen.cursor.x * self._char_width
            cy = self._screen.cursor.y * self._char_height
            painter.fillRect(cx, cy, self._char_width, self._char_height, CURSOR_COLOR)

        painter.end()

    def _to_qcolor(self, color_str):
        if color_str in ANSI_COLORS:
            return ANSI_COLORS[color_str]
        return DEFAULT_FG

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
```

- [ ] **Step 2: Verify import**

```bash
python -c "from ui.terminal_widget import TerminalWidget; print('TerminalWidget OK')"
```
Expected: `TerminalWidget OK`

- [ ] **Step 3: Commit**

```bash
git add ui/__init__.py ui/terminal_widget.py
git commit -m "feat: add terminal widget with pyte rendering and keyboard handling"
```

---

### Task 5: Main window

**Files:**
- Create: `ui/main_window.py`

- [ ] **Step 1: Implement MainWindow**

`ui/main_window.py`:
```python
import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt
from store.path_history import PathHistory
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import TerminalWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyTerm")
        self.resize(900, 550)

        self._history = PathHistory()
        self._backend = TerminalBackend()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(8, 8, 8, 8)
        topbar_layout.setSpacing(6)

        self._path_combo = QComboBox()
        self._path_combo.setEditable(True)
        self._path_combo.setMinimumWidth(300)
        self._path_combo.setStyleSheet(
            "QComboBox { font-family: Consolas; font-size: 13px; padding: 4px 8px; "
            "border: 1px solid #555; border-radius: 3px; background: #1e1e1e; color: #ccc; }"
            "QComboBox QAbstractItemView { background: #1e1e1e; color: #ccc; "
            "selection-background-color: #094771; }"
        )
        self._load_history()
        topbar_layout.addWidget(self._path_combo, 1)

        self._launch_btn = QPushButton("启动")
        self._launch_btn.setFixedHeight(30)
        self._launch_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 20px; "
            "background: #0e639c; color: white; border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #1177bb; }"
            "QPushButton:pressed { background: #094771; }"
        )
        self._launch_btn.clicked.connect(self._on_launch)
        topbar_layout.addWidget(self._launch_btn)

        layout.addWidget(topbar)

        # Terminal
        self._terminal = TerminalWidget(self._backend)
        layout.addWidget(self._terminal, 1)

        self.setStyleSheet("QMainWindow { background: #1e1e1e; }")

    def _load_history(self):
        paths = self._history.all()
        self._path_combo.clear()
        self._path_combo.addItems(paths)
        if paths:
            self._path_combo.setCurrentText(paths[0])

    def _on_launch(self):
        path = self._path_combo.currentText().strip()
        if not path:
            QMessageBox.warning(self, "错误", "请输入路径")
            return
        if not os.path.isdir(path):
            QMessageBox.warning(self, "错误", f"路径不存在:\n{path}")
            return

        self._history.add(path)
        self._load_history()
        self._backend.start_shell(cwd=path)
        self._terminal.setFocus()
```

- [ ] **Step 2: Verify import**

```bash
python -c "from ui.main_window import MainWindow; print('MainWindow OK')"
```
Expected: `MainWindow OK`

- [ ] **Step 3: Commit**

```bash
git add ui/main_window.py
git commit -m "feat: add main window with path combo, history, and launch button"
```

---

### Task 6: Entry point

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write main.py**

```python
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import**

```bash
python -c "import main; print('main OK')"
```
Expected: `main OK`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add application entry point"
```

---

### Task 7: Smoke test and fix issues

- [ ] **Step 1: Launch the application**

```bash
python main.py &
```
Manual verification checklist:
- [ ] Window appears with path combo and "启动" button
- [ ] Type `C:\` in path box, click "启动" → PowerShell launches
- [ ] Type commands (`dir`, `echo hello`) → output renders correctly
- [ ] Type `powershell -c "Get-ChildItem"` → colored output
- [ ] Resize window → terminal columns/rows adjust
- [ ] Close terminal output → see "Process exited with code 0"
- [ ] Launch again with a different path → works
- [ ] Path history persists across launches (check combo dropdown)

- [ ] **Step 2: Fix issues found during smoke test**

Fix any rendering or input issues discovered above.

- [ ] **Step 3: Commit fixes**

```bash
git add -A
git commit -m "fix: smoke test corrections for terminal rendering and input"
```
