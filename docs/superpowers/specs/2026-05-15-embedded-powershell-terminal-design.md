# Requirement 1: Embedded PowerShell Terminal

## Goal
Build a Windows GUI that can launch an embedded PowerShell session in a user-specified directory, with path history support.

## Architecture

```
MainWindow
├── TopBar (路径栏)
│   ├── QComboBox (可编辑 + 下拉历史记录，记录最近10条路径)
│   └── QPushButton ("启动")
└── TerminalWidget (自绘 QWidget，填满剩余空间)
    ├── pyte.Screen    — 终端状态（字符网格、光标、颜色）
    ├── pyte.Stream    — ANSI 转义序列解析器
    └── pywinpty.PtyProcess — Windows ConPTY 封装
```

## Data Flow

1. User clicks "启动"
   - Read current path from QComboBox
   - pywinpty creates ConPTY, spawns powershell.exe (cwd=specified path)
   - Start read thread to poll PTY output
     - pyte.Stream.feed(data) parses ANSI
     - pyte.Screen updates character grid state
     - TerminalWidget.repaint() redraws
   - Success: path saved to history (dedup, keep last 10)
   - Failure: error dialog

2. User types in terminal
   - TerminalWidget.keyPressEvent()
   - Convert to bytes, write to pywinpty
   - Sent to powershell.exe

## Components

### Path History
- Store: QSettings (ini file), keyed as JSON array
- Behavior: dedup on add, max 10 entries, most recent first
- Load on startup, save on each successful launch

### Terminal Rendering
- Custom QWidget with paintEvent override
- Fixed-width font (Consolas, 14pt)
- Render from pyte.Screen: for each row, draw characters with QPainter
- Support: foreground/background colors, bold, underline, blink cursor
- Scrollback: keep pyte.Screen history buffer

### Terminal Backend
- QThread for reading PTY output, signal to main thread on data ready
- Write method: encode text to bytes, write to PTY stdin
- Handle process exit: detect, signal to UI, show exit code
- Resize: on widget resize, send new size to ConPTY

## File Structure

```
MyTerm/
├── main.py              # Entry point, create QApplication + MainWindow
├── ui/
│   ├── main_window.py   # Main window layout (top bar + terminal)
│   └── terminal_widget.py  # Terminal rendering + keyboard input handling
├── backend/
│   └── terminal_backend.py # pywinpty process management + read/write thread
├── store/
│   └── path_history.py  # Path history: QSettings read/write, dedup, max 10
└── requirements.txt     # PySide6, pywinpty, pyte
```

## Dependencies
- PySide6 >= 6.5 (Qt for Python, LGPL)
- pywinpty >= 2.0 (Windows ConPTY wrapper)
- pyte >= 0.8 (terminal emulator / ANSI parser)

## Out of Scope (future requirements)
- SSH connections
- Multiple tabs
- Split views
- Font/color configuration
- Copy/paste
- Session logging
