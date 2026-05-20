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

### 前置依赖

- Python 3.10+（开发与发版用 3.14），并跑过 `pip install -r requirements.txt`
- PyInstaller：`pip install pyinstaller`
- Pillow：`pip install pillow`（生成 `icon.ico` 用）
- Inno Setup 6：[官网下载](https://jrsoftware.org/isinfo.php) 默认安装即可，
  `release.bat` 会从 `Program Files (x86)\Inno Setup 6` 自动找 `ISCC.exe`
- 中文界面用户额外下载 `ChineseSimplified.isl` 放到 Inno Setup 的 `Languages\` 目录

### 一键发布

```bat
scripts\release.bat
```

脚本顺序干这几件事：

1. 从 `version.py` 读 `__version__`
2. `python scripts\make_icon.py` 把 `icon.png` 转多尺寸 `icon.ico`
3. 清空 `build/` `dist/`，跑 `python -m PyInstaller myterm.spec` 出 `dist\MyTerm.exe`
4. 跑 Inno Setup 编译 `installer\myterm.iss`，出 `dist\MyTerm-Setup-<version>.exe`

### 产物

- `dist\MyTerm.exe` — 单文件 EXE（约 50 MB），可直接分发，双击运行
- `dist\MyTerm-Setup-<version>.exe` — Inno Setup 安装包，用户级安装到
  `%LOCALAPPDATA%\Programs\MyTerm\`，无需管理员权限，自动建开始菜单快捷方式

> `build/` `dist/` `icon.ico` 都是构建派生物，已经在 `.gitignore` 中，
> 不入库。需要分发安装包时，把 `dist\MyTerm-Setup-<version>.exe` 上传到
> Releases 页面或内部分发渠道。

### 发新版

1. 改 `version.py` 的 `__version__`
2. `scripts\release.bat`
3. 把 `dist\MyTerm-Setup-<version>.exe` 上传到分发渠道

### 单步打包

只想出 EXE，不打安装包：

```bash
python -m PyInstaller myterm.spec
```

只想用现成 EXE 重新打安装包：

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 installer\myterm.iss
```

清理后重来：

```bash
rm -rf build dist
```

更详细的运行时目录约定、首启迁移、spec 关键设定见 [docs/packaging.md](docs/packaging.md)。

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

