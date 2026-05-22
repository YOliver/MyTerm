# 使用说明

MyTerm 是一个 Windows 桌面终端模拟器，下面按界面区域 → 操作 → 快捷键的顺序介绍常用功能。

## 主界面

启动后窗口分三层：

1. **菜单栏**：环境（依赖检测）、设置（AI CLI 配置）、帮助（本说明 / 软件信息）
2. **顶部工具栏**：工作目录下拉、Shell 预设下拉、浏览、启动
3. **终端网格区**：底部主体，启动后在此显示终端

## 启动一个终端

1. 在路径下拉框选历史目录，或点「浏览」选新目录（路径会自动加入历史）
2. 选 Shell 预设（默认两条：`powershell` / `cmd`，其它由你自己在「设置 → AI CLI 配置」里加，见下文）
3. 点「启动」——一个新终端会出现在网格区

每个终端 tile 顶部显示「目录名 + Shell 标签」，右上角 × 关闭。

## AI CLI 配置

下拉框里出现哪些 shell / AI CLI，完全由你自己配置。新装时只默认两条 `powershell` 和 `cmd`，其它按需自己加，这样新装一个 AI CLI 不用等软件升级。

### 入口

菜单栏 **设置 → AI CLI 配置...**

### 字段说明

| 字段 | 含义 |
|------|------|
| **标签** | 启动下拉框里显示的名字，也用来在保存后回填上次的选择 |
| **宿主** | 三选一：`powershell` / `cmd` / `none`，决定外层怎么包裹你的命令 |
| **命令** | 在宿主里要执行的命令 |

### 宿主选哪个

| 你的 AI CLI 长啥样 | 宿主 | 命令填什么 |
|------|------|------|
| npm 全局装的（`claude`、`codebuddy` 这种 .cmd 命令） | `powershell` | `claude` |
| 想跑带参数的（如 `claude -r` 续接最近会话） | `powershell` | `claude -r` |
| 习惯在 cmd 下跑 | `cmd` | `codebuddy` |
| 直接启个 shell 本身（bash、wsl、pwsh 等） | `none` | `bash.exe` 或 `wsl.exe` |

底层规则：

- `powershell` → 自动包成 `powershell.exe -NoExit -Command <你的命令>`
- `cmd` → 自动包成 `cmd.exe /K <你的命令>`（用 `/K` 不是 `/C`，命令跑完会保留 cmd 会话不闪退）
- `none` → 直接当 argv，用 Windows 风格分词，**带空格的路径要用双引号包住**，例如：`"C:\Program Files\Git\bin\bash.exe" --login`

### 操作按钮

- **新增**：在选中行下方插入一行，自动进入编辑（默认值是 `新预设 / powershell / 空命令`）
- **删除**：删选中行（至少保留一条）
- **↑ / ↓**：调整顺序，顺序就是启动下拉框里的顺序
- **保存**：写盘 + 立即刷新主窗口下拉框，**已开的终端不受影响**
- **取消**：全部丢弃，不写盘

### 几个常用配置示例

```
标签              宿主         命令
─────────────────────────────────────────────────
powershell        none         powershell.exe
cmd               none         cmd.exe
claude            powershell   claude
claude -r         powershell   claude -r
claude-internal   powershell   claude-internal
codebuddy         powershell   codebuddy
gemini            powershell   gemini
git-bash          none         "C:\Program Files\Git\bin\bash.exe" --login
wsl               none         wsl.exe
```

### 配置文件位置（想直接手改也行）

`%LOCALAPPDATA%\MyTerm\shell_presets.json`，JSON 结构：

```json
{
  "version": 1,
  "presets": [
    {"label": "claude", "host": "powershell", "command": "claude"}
  ]
}
```

文件损坏或字段非法时**不会覆盖你的手改**，会回退到默认两条并在错误日志里给出提示；启动后从「设置」面板里再保存一次即可重新生成正确的文件。

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

菜单栏 **环境 → 检测依赖** 可一次性检查本机以下基础工具的安装状态与版本：

- Node.js / npm
- Python / Git

每项显示版本号、可执行文件路径，未安装或调用超时会有相应提示。

> AI CLI（claude / codebuddy 等）不在此处检测——它们由你自己装、自己在「设置 → AI CLI 配置」里登记，能不能跑起来在下拉框里点启动就知道。

## 数据存储位置

- 路径历史：`%LOCALAPPDATA%\MyTerm\path_history.json`
- AI CLI 预设：`%LOCALAPPDATA%\MyTerm\shell_presets.json`
- 粘贴的图片缓存：`%LOCALAPPDATA%\MyTerm\Cache\paste\`

卸载时不会删除以上数据。
