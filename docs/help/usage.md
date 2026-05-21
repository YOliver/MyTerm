# 使用说明

MyTerm 是一个 Windows 桌面终端模拟器，下面按界面区域 → 操作 → 快捷键的顺序介绍常用功能。

## 主界面

启动后窗口分三层：

1. **菜单栏**：环境（依赖检测）、帮助（本说明 / 软件信息）
2. **顶部工具栏**：工作目录下拉、Shell 预设下拉、浏览、启动
3. **终端网格区**：底部主体，启动后在此显示终端

## 启动一个终端

1. 在路径下拉框选历史目录，或点「浏览」选新目录（路径会自动加入历史）
2. 选 Shell 预设（见下表）
3. 点「启动」——一个新终端会出现在网格区

| 预设 | 说明 |
|------|------|
| powershell | 原生 PowerShell |
| claude -r | PowerShell 中启动 `claude -r`（续接最近会话）；当前目录无历史会话时自动退化为 `claude` |
| codebuddy | PowerShell 中启动 `codebuddy` |
| claude-internal | PowerShell 中启动 `claude-internal` |
| cmd | 原生 cmd.exe |

每个终端 tile 顶部显示「目录名 + Shell 标签」，右上角 × 关闭。

## 多终端布局

- 同时最多 **4 个**终端
- 网格自动按数量调整：1 → 1×1，2 → 1×2，3 / 4 → 2×2
- 关闭其中一个会重新平铺，剩下的填满剩余空间

## 快捷键

### 文本操作

- `Ctrl+C`：**有选区**时复制；**无选区**时发送中断（SIGINT）给当前进程
- `Ctrl+Shift+C`：强制复制选区，永远不发送中断
- `Ctrl+V`：粘贴。剪贴板里是图片（截图、浏览器复制的图等）会自动落盘并把路径写入终端
- `Ctrl+D` / `Ctrl+Z`：透传 EOF / SUB

### 行编辑（透传给 shell，由 PSReadLine / readline 解释）

- `Ctrl+W` / `Ctrl+Backspace`：删除光标前一个单词
- `Ctrl+U`：删除从光标到行首
- `Ctrl+K`：删除从光标到行尾
- `Ctrl+A` / `Ctrl+E`：跳到行首 / 行尾
- `Ctrl+L`：清屏

> 提示：粘贴含换行的多行文本后，PSReadLine 会把整段当成一行处理，`Ctrl+U` 可能被换行符卡住。此时可按两次 `Esc` 撤销整段输入。

### 滚动历史

- `Shift+PageUp` / `Shift+PageDown`：上下翻一屏
- `Shift+Home` / `Shift+End`：跳到历史顶部 / 底部
- 鼠标滚轮：每滚一格滚 1 行

历史缓冲保留最近 **2000 行**。

### 方向键 / 编辑键

- `↑` / `↓`：透传，shell 会用来翻命令历史
- `Home` / `End` / `Delete` / `PageUp` / `PageDown`：透传给前台程序（vim、less 等可用）

## 鼠标操作

- **左键拖选**：选中文本（跨行可选）
- **双击**：按非空白字符边界选中一个「词」
- **右键**：有选区时把选区直接发送给终端（不经剪贴板）；无选区时粘贴剪贴板（行为对齐 Windows Terminal）

## 图片粘贴

剪贴板里有图片（QQ 截图、浏览器复制图片、`Win+Shift+S` 截屏等）时，按 `Ctrl+V` 或右键粘贴会：

1. 把图片以 PNG 格式保存到缓存目录 `%LOCALAPPDATA%\MyTerm\Cache\paste\`
2. 把保存后的文件路径以 PowerShell 友好的格式写入终端

这样可以直接把截图喂给 claude / codebuddy / claude-internal 等支持读图的 CLI 工具。

## 输入法

完整支持中文输入法（微软拼音、搜狗等），输入候选框会跟随光标位置。

## 环境检测

菜单栏 **环境 → 检测依赖** 可一次性检查本机以下工具的安装状态与版本：

- Node.js / npm
- Python / Git
- claude / claude-internal / codebuddy

每项显示版本号、可执行文件路径，未安装或调用超时会有相应提示。

## 数据存储位置

- 路径历史：`%LOCALAPPDATA%\MyTerm\path_history.json`
- 粘贴的图片缓存：`%LOCALAPPDATA%\MyTerm\Cache\paste\`

卸载时不会删除以上数据。
