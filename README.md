# MyTerm

> 一个面向 Windows 的现代终端模拟器，原生集成 AI CLI 一键安装、跨终端选区共享、剪贴板图片粘贴等开箱即用的能力。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](#许可证)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#依赖)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](#)

技术栈：**Python + PySide6 + pywinpty + pyte**。

---

## ✨ 特性

### 终端体验
- **真彩色 ANSI 渲染** — 16 色 / 256 色 / 真彩色，PowerShell 原生配色直接还原
- **多终端平铺** — 同时最多 4 个独立会话，自动 1/2/2×2 网格平铺
- **鼠标全套交互** — 拖选 / 双击选词 / 右键智能复制粘贴 / 滚轮翻历史
- **跨终端选区共享** — A 终端选中、B 终端右键，直接发送 A 的选区文本（对齐 Windows Terminal 体验）
- **2000 行回滚** — `Shift+PageUp/Down`、`Shift+Home/End`、滚轮均可翻
- **中文 IME 友好** — 微软拼音 / 搜狗候选框跟随光标
- **字符宽度正确** — Braille / Box Drawing / CJK 等特殊字符不串位

### AI CLI 集成
- **CLI 一键安装/卸载** — 内置 5 家 AI CLI 安装脚本，菜单点一下就装好
  - Claude Code (`@anthropic-ai/claude-code`)
  - CodeBuddy Code (`@tencent-ai/codebuddy-code`)
  - Codex CLI (`@openai/codex`)
  - Gemini CLI (`@google/gemini-cli`)
  - Qwen Code (`@qwen-code/qwen-code`)
- **启动预设联动** — 装完自动追加进启动下拉框，卸载时自动回收
- **可视化预设管理** — 「设置 → AI CLI 配置」对话框，标签/宿主/命令三列表格直接改

### 工程化能力
- **剪贴板图片粘贴** — `Ctrl+V` 截图自动落盘，路径写入终端，方便喂给支持读图的 AI CLI
- **路径历史** — 工作目录下拉自动记忆
- **环境依赖检测** — 一键检测 Node.js / npm / Python / pip / Git
- **内置使用说明** — 「帮助 → 使用说明」就地查阅，不必离开应用

---

## 📦 下载与安装

### 普通用户：装安装包

到 [Releases](https://github.com/YOliver/MyTerm/releases) 下载最新的 `MyTerm-Setup-<version>.exe`，双击安装即可。

- **安装位置**：`%LOCALAPPDATA%\Programs\MyTerm\`（用户级，**无需管理员权限**）
- **启动入口**：开始菜单 → MyTerm
- **卸载**：控制面板 → 程序与功能 → MyTerm（用户数据保留在 `%LOCALAPPDATA%\MyTerm\`）

也可下载绿色版 `MyTerm.exe`，放任意目录双击运行，不写注册表。

### 开发者：从源码运行

```bash
git clone https://github.com/YOliver/MyTerm.git
cd MyTerm
pip install -r requirements.txt
python main.py
```

> 开发模式下配置/历史等运行时文件全部落在工程根（`shell_presets.json` / `path_history.json`），便于调试；打包模式自动写入 `%LOCALAPPDATA%\MyTerm\`。

---

## 🚀 快速上手

启动后窗口分三层：

1. **菜单栏**：环境 / 设置 / 帮助
2. **顶部工具栏**：工作目录下拉 + Shell 预设下拉 + 浏览按钮 + 启动按钮
3. **终端网格区**：启动后在此显示终端

**最短路径开一个终端**：

1. 工具栏「浏览」选目录（也可在下拉里直接选历史）
2. Shell 下拉选 `powershell`（默认就有）
3. 点「启动」

需要装 AI CLI？菜单「设置 → CLI 安装」勾选要装的，等 npm 跑完就行——装完启动下拉里会自动多出一项。

完整功能说明（菜单/快捷键/鼠标/图片粘贴/数据存储位置等）见 [`helpdocs/使用手册.md`](helpdocs/使用手册.md)，也可在应用内「帮助 → 使用手册」查阅。

---

## ⌨️ 常用快捷键速查

| 操作 | 快捷键 |
|---|---|
| 复制选区（无选区时发送 SIGINT） | `Ctrl+C` |
| 强制复制选区 | `Ctrl+Shift+C` |
| 粘贴（图片自动落盘） | `Ctrl+V` |
| 跨终端复制 | 在 A 选中 → 在 B **右键** |
| 翻历史 | `Shift+PageUp/Down`、`Shift+Home/End`、滚轮 |
| 清屏 | `Ctrl+L` |
| 删一个单词 / 到行首 / 到行尾 | `Ctrl+W` / `Ctrl+U` / `Ctrl+K` |

---

## 🛠️ 构建发布

> 普通用户可跳过本节，直接到 [Releases](https://github.com/YOliver/MyTerm/releases) 下载。

### 前置依赖

- Python 3.10+（开发与发版用 3.14）
- PyInstaller：`pip install pyinstaller`
- Pillow：`pip install pillow`（`scripts/make_icon.py` 生成 `icon.ico` 用）
- Inno Setup 6：[官网下载](https://jrsoftware.org/isinfo.php) 默认安装即可，
  `release.bat` 会从 `Program Files (x86)\Inno Setup 6` 自动找 `ISCC.exe`
- 中文界面的 Inno Setup 还需额外下载 `ChineseSimplified.isl` 放到 Inno Setup 的 `Languages\` 目录

### 一键发布

```bat
scripts\release.bat
```

脚本依次做：

1. 从 `version.py` 读 `__version__`
2. `python scripts\make_icon.py` 把 `icon.png` 转多尺寸 `icon.ico`
3. 清空 `build/` `dist/`，跑 `python -m PyInstaller myterm.spec` 出 `dist\MyTerm.exe`
4. 跑 Inno Setup 编译 `installer\myterm.iss`，出 `dist\MyTerm-Setup-<version>.exe`

### 产物

| 文件 | 形态 | 适用 |
|---|---|---|
| `dist\MyTerm.exe` | 单文件绿色 EXE（≈50 MB） | 拷贝即用，不写注册表 |
| `dist\MyTerm-Setup-<version>.exe` | Inno Setup 安装包 | 用户级安装，自动建开始菜单快捷方式 |

> `build/` `dist/` `icon.ico` 都是构建派生物，已在 `.gitignore` 中，不入库。

### 发新版流程

1. 改 `version.py` 的 `__version__`
2. 跑 `scripts\release.bat`
3. 把 `dist\MyTerm-Setup-<version>.exe` 上传到 GitHub Release（或内部分发渠道）

### 单步操作

只出 EXE，不打安装包：

```bash
python -m PyInstaller myterm.spec
```

只用现成 EXE 重新打安装包：

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.2.2 installer\myterm.iss
```

清理后重来：

```bash
rm -rf build dist
```

更详细的运行时目录约定、首启迁移、spec 关键设定见 [`docs/packaging.md`](docs/packaging.md)。

---

## 📐 架构

```
PowerShell → pywinpty → QThread → pyte.Stream → HistoryScreen → QPainter
```

| 目录 | 职责 |
|---|---|
| `backend/` | PTY 进程管理（pywinpty + QThread 桥接） |
| `ui/` | 主窗口、终端 widget、各对话框（环境检测/CLI 安装/AI CLI 配置/帮助） |
| `store/` | 配置/历史/预设持久化，环境检测，CLI installer 发现器 |
| `scripts/cli_installers/` | 各家 AI CLI 的 install/uninstall 脚本（每个一个 `.py`） |
| `installer/` | Inno Setup 脚本，打用户级 Windows 安装包 |
| `tests/` | pytest 测试套件 |
| `docs/` | 帮助文档、打包说明、内部设计稿 |

---

## 📋 依赖

运行时（`requirements.txt`）：

- **PySide6** — Qt GUI 绑定
- **pywinpty** — Windows ConPTY 封装
- **pyte** — ANSI 转义序列解析
- **wcwidth** — Unicode 宽字符检测

开发时额外：`pytest`（测试）、`pyinstaller`（打包）、`pillow`（图标生成）。

---

## 🤝 贡献与反馈

- Bug / 需求：欢迎提 [Issue](https://github.com/YOliver/MyTerm/issues)
- 代码贡献：直接发 PR
- 邮件：740614279@qq.com

提 Issue 前可以先跑一遍：

```bash
pytest -q
```

——若有失败用例先附在 Issue 里。

---

## 📄 许可证

MIT © oliveryin
