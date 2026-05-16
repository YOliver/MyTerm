# MyTerm

Windows 终端仿真器，Python + PySide6 + pywinpty + pyte。

## 特性

- **真彩色终端** — 支持 16 色、256 色和真彩色 ANSI 渲染，显示 PowerShell 原版配色
- **多终端平铺** — 2×2 网格，最多 4 个独立 PowerShell 会话同时运行
- **鼠标选择复制** — 拖选文本高亮，Ctrl+C 复制到剪贴板，双击选词
- **回滚滚动** — 2000 行历史，鼠标滚轮翻阅
- **字体回退** — 正确处理 Braille、Box Drawing 等特殊 Unicode 字符
- **中文 IME** — 支持微软拼音等输入法

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

## 依赖

- Python 3.10+
- PySide6 — Qt GUI
- pywinpty — Windows ConPTY 封装
- pyte — ANSI 转义序列解析
- wcwidth — 宽字符检测

## 架构

```
PowerShell → winpty → QThread → pyte.Stream → HistoryScreen → QPainter
```

- `backend/` — PTY 进程管理（QThread）
- `ui/` — 终端渲染和主窗口
- `store/` — 路径历史持久化

## 许可证

MIT
