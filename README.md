# MyTerm

Windows 终端仿真器，Python + PySide6 + pywinpty + pyte。

## 特性

- **真彩色终端** — 支持 16 色、256 色和真彩色 ANSI 渲染，显示 PowerShell 原版配色
- **多终端平铺** — 2×2 网格，最多 4 个独立 PowerShell 会话同时运行
- **鼠标选择复制** — 拖选文本高亮，Ctrl+C 复制到剪贴板,双击选词
- **回滚滚动** — 2000 行历史，鼠标滚轮翻阅
- **字体回退** — 正确处理 Braille、Box Drawing 等特殊 Unicode 字符
- **中文 IME** — 支持微软拼音等输入法

## 安装使用（普通用户）

下载 `MyTerm-Setup-<version>.exe` 双击安装。

- 安装位置：`%LOCALAPPDATA%\Programs\MyTerm\`（用户级，无需管理员权限）
- 启动入口：开始菜单 → MyTerm
- 卸载：控制面板 → 程序与功能 → MyTerm（用户数据保留在 `%APPDATA%\MyTerm`）

## 从源码运行（开发者）

```bash
pip install -r requirements.txt
python main.py
```

开发模式下配置/历史等运行时文件全部落在工程根，便于调试。

## 构建安装包

一键发布：

```bat
scripts\release.bat
```

产物：

- `dist\MyTerm.exe` — PyInstaller 单文件
- `dist\MyTerm-Setup-<version>.exe` — Inno Setup 安装包

发布前置依赖、目录约定、首启迁移、spec 细节等见 [docs/packaging.md](docs/packaging.md)。

发新版只需改 `version.py` 里的 `__version__`，再跑 `scripts\release.bat`。

## 依赖

- Python 3.10+（开发与打包用 3.14）
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
- `store/` — 路径解析、配置、历史持久化
- `installer/`、`scripts/` — 打包发布相关

## 许可证

MIT

