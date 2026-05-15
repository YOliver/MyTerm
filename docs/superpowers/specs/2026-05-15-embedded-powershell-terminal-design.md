# Requirement 1: Embedded PowerShell Terminal

## Goal
Build a Windows GUI that can launch an embedded PowerShell session in a user-specified directory, with path history support.

## Architecture

```
MainWindow
├── TopBar (路径栏)
│   ├── QComboBox (下拉历史记录，记录最近10条路径，不可编辑)
│   ├── QPushButton ("浏览") — 弹出 QFileDialog.getExistingDirectory
│   └── QPushButton ("启动")
└── TerminalWidget (自绘 QWidget，填满剩余空间)
    ├── pyte.Screen    — 终端状态（字符网格、光标、颜色）
    ├── pyte.Stream    — ANSI 转义序列解析器
    ├── wcwidth        — 检测 CJK 双宽字符
    └── pywinpty.PtyProcess — Windows ConPTY 封装
```

## Data Flow

1. User clicks "浏览" → QFileDialog 弹出 → 选取路径 → 填入 QComboBox + 存入历史
2. User clicks "启动"
   - Read current path from QComboBox
   - Read terminal dimensions from pyte.Screen (columns, lines)
   - pywinpty creates ConPTY with matching dimensions, spawns powershell.exe (cwd=specified path)
   - Start QThread read loop to poll PTY output
     - pyte.Stream.feed(data) parses ANSI
     - pyte.Screen updates character grid state
     - TerminalWidget.repaint() redraws
   - Success: path saved to history (dedup, keep last 10)
   - Failure: error dialog

3. User types in terminal
   - ASCII: TerminalWidget.keyPressEvent() → backend.write(text)
   - CJK/IME: TerminalWidget.inputMethodEvent() → backend.write(commitString)
   - Bytes sent to pywinpty → powershell.exe

4. Window resize
   - resizeEvent → 200ms debounce → _apply_resize
   - Recalculates cols/rows from widget size ÷ font metrics
   - Screen.resize(rows, cols) [note: pyte API is resize(lines, columns)]
   - Backend.resize(cols, rows) → PTY setwinsize(rows, cols)

## Components

### Path Selection (优化需求)
- QComboBox: 下拉展示历史路径（最近10条），不可手动编辑
- "浏览" 按钮: 调用 QFileDialog.getExistingDirectory 选择目录
- 浏览选中的路径自动加入历史并刷新下拉列表

### Path History
- Store: JSON file at project root (path_history.json)
- Behavior: dedup on add, max 10 entries, most recent first
- Load on startup, save on each add

### Terminal Rendering
- Custom QWidget with paintEvent override
- Fixed-width font (Consolas, 14pt)
- Render from pyte.Screen.buffer
- Support: foreground/background ANSI colors, bold, blink cursor
- CJK wide chars: detect with wcwidth.wcwidth(), draw 2× cell width, skip placeholder column
- Cursor: blinking solid rectangle at screen.cursor position

### IME Input (优化需求)
- WA_InputMethodEnabled attribute
- inputMethodEvent: committed text → backend.write()
- inputMethodQuery: return cursor rectangle for IME candidate window

### Terminal Backend
- QThread for reading PTY output, signal to main thread on data ready
- Write method: send str to PTY (pywinpty accepts str, not bytes)
- Read method: pty.read(4096) — blocking by default, no `blocking` parameter
- Handle re-launch: stop old process before starting new one
- Resize: on widget resize, send new size to PTY via setwinsize(rows, cols)
- ptyspawn dimensions parameter: (rows, columns) — rows first

### Launcher (优化需求)
- 启动.bat: `start "" pythonw main.py` — no console window, bat closes immediately

## File Structure

```
MyTerm/
├── main.py              # Entry point, create QApplication + MainWindow
├── 启动.bat              # One-click launcher (pythonw, no console)
├── ui/
│   ├── main_window.py   # Main window: path combo + browse btn + launch btn + terminal
│   └── terminal_widget.py  # Terminal: pyte rendering, CJK, IME, keyboard
├── backend/
│   └── terminal_backend.py # pywinpty ConPTY wrapper (QThread)
├── store/
│   └── path_history.py  # Path history: JSON persist, dedup, max 10
├── tests/
│   └── test_path_history.py  # 5 tests
└── requirements.txt     # PySide6, pywinpty, pyte, wcwidth
```

## Dependencies
- PySide6 >= 6.5 (Qt for Python, LGPL)
- pywinpty >= 2.0 (Windows ConPTY wrapper)
- pyte >= 0.8 (terminal emulator / ANSI parser)
- wcwidth (CJK character width detection, pyte dependency)

## Out of Scope (future requirements)
- SSH connections
- Multiple tabs
- Split views
- Font/color configuration
- Copy/paste
- Session logging
