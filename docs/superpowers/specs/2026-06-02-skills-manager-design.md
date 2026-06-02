# Skills 管理器

> 将 Skills 从"设置"子菜单提升为顶级菜单，提供按 CLI 分组浏览、启用/禁用、预览 SKILL.md 的能力。

## 目标

用户在 MyTerm 菜单栏点"Skills"后，弹出对话框，按 CLI（Claude Code / CodeBuddy / Codex / Gemini / Qwen Code）分组展示各自全局 skills 目录下的 skill 清单，支持：

- 浏览 — 查看所有已安装 skills（名称 + 描述）
- 启用/禁用 — checkbox 切换，文件级移动实现
- 查看内容 — 内置预览弹窗显示 SKILL.md 原文
- 打开目录 — 在资源管理器打开对应 CLI 的 skills 文件夹

## 菜单变更

```
菜单栏: 环境 | 设置 | Skills | 日志 | 帮助
```

Skills 从 `设置 → skills` 子菜单项提升为顶级菜单，点击直接打开 Skills 管理对话框。

## 对话框布局

```
┌──────────────────────────────────────────────────────┐
│  Skills 管理                                    [×]  │
├──────────┬───────────────────────────────────────────┤
│          │                                           │
│ Claude   │  ☑ brainstorming                         │
│ Code     │    You MUST use this before any creative… │
│ (16)     │                                           │
│          │  ☑ dispatching-parallel-agents            │
│ CodeBuddy│    Use when facing 2+ independent tasks…  │
│ (16)     │                                           │
│          │  ☐ writing-skills                         │
│ Codex    │                                           │
│ (0)      │  [打开目录]  [查看 SKILL.md]               │
│          │                                           │
│ Gemini   │                                           │
│ (0)      │                                           │
│          │                                           │
│ Qwen     │                                           │
│ (0)      │                                           │
└──────────┴───────────────────────────────────────────┘
```

- **左侧**：CLI 列表，显示名称 + skills 数量。数量 0 的灰色显示
- **右侧**：skill 清单（名称 + 描述），每项前有 checkbox
- **底部按钮**：`打开 Skills 目录` / `查看 SKILL.md`

## 启用/禁用机制

文件系统移动方案，简单可靠：

```
~/.claude/
├── skills/              ← CLI 从这里加载（启用的 skill）
│   ├── brainstorming/
│   └── ...
└── skills-disabled/     ← 禁用后移到这里
    └── writing-skills/
```

- **禁用**：`skills/{name}/` → `skills-disabled/{name}/`（`shutil.move`）
- **启用**：`skills-disabled/{name}/` → `skills/{name}/`
- 若 `skills-disabled/` 不存在，操作时自动创建
- 操作后自动刷新右侧列表

## 文件结构（遵循三层模式）

```
store/
├── skills_manager.py     ← 纯逻辑：扫描/移动/读取 skill（无 Qt 依赖）
ui/
├── skills_dialog.py      ← Dialog + 布局 + 预览弹窗
ui/
├── main_window.py        ← 菜单注册（Skills 提升为顶级菜单）
tests/
├── test_skills_manager.py ← 单测
```

## 各层职责

### store/skills_manager.py — 纯逻辑

- `CLI_SKILLS_DIRS: dict[str, Path]` — 写死各 CLI 的 skills 根目录映射
  - `claude_code` → `~/.claude/skills/`
  - `codebuddy` → `~/.codebuddy/skills/`
  - `codex` → `~/.codex/skills/`
  - `gemini` → `~/.gemini/skills/`
  - `qwen_code` → `~/.qwen/skills/`
- `SkillInfo(name, description, enabled, cli_id)` — dataclass
- `scan_skills(cli_id) -> list[SkillInfo]` — 扫描 skills + skills-disabled 目录，解析 SKILL.md frontmatter
- `set_skill_enabled(cli_id, name, enabled) -> bool` — 移动目录，返回成功/失败
- `load_skill_content(cli_id, name, enabled) -> str` — 读取 SKILL.md 全文
- `open_skills_dir(cli_id)` — `os.startfile(str(path))`

### ui/skills_dialog.py — UI

- `SkillsDialog(QDialog)` — 主对话框：
  - 左侧 QListWidget（CLI 列表）
  - 右侧 QScrollArea + 动态 checkbox 列表
  - 底部按钮栏
- `SkillPreviewDialog(QDialog)` — 预览弹窗：
  - QPlainTextEdit（只读，等宽字体，深色主题）
- 样式常量 `_SKILLS_STYLE`

### ui/main_window.py — 菜单注册

- `_build_menubar` 中新增 `skills_menu = menubar.addMenu("Skills")`
- 移除 `settings_menu` 中旧的 skills action + `_on_open_skills`

## 边界处理

| 场景 | 处理 |
|---|---|
| CLI 未安装（skills 目录不存在） | 数量显示 0，右侧提示"该 CLI 未安装或无全局 skills" |
| skill 目录缺少 SKILL.md | 名称用目录名，描述显示"(无描述)" |
| SKILL.md 无 frontmatter | 名称用目录名，描述取文件首行 |
| 移动失败（权限/被占用） | `shutil.move` 抛异常，dialog 捕获后 QMessageBox 报错 |
| skills-disabled 目录不存在 | 首次移动时自动创建 |

## 测试策略

`store/skills_manager.py` 纯函数无 Qt 依赖，用 pytest + tmp_path 隔离环境测：

- 扫描空目录返回空列表
- 扫描含多个 skill 的目录
- 解析有/无 frontmatter 的 SKILL.md
- 启用→禁用→启用 来回切换
- 打开不存在的目录不抛异常

## 参考实现

- 逻辑层模式：`store/env_check.py`
- UI 层模式：`ui/env_check_dialog.py`、`ui/shell_presets_dialog.py`
- 菜单注册：`ui/main_window.py:_build_menubar`
