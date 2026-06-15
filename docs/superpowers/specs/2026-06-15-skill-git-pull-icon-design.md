# Skills 列表 Git 更新图标

> 在 Skills 浏览界面每个 skill 名称前添加更新箭头图标，git 管理的 skill 可一键 pull，非 git 管理的图标置灰。

## 目标

在 `SkillsDialog` 右侧 skill 列表的每一行名称前增加一个更新箭头图标：

- git 管理的 skill：图标可点击，点击后执行 `git pull`，弹窗提示成功/失败
- 非 git 管理的 skill：图标置灰，不可点击

## 检测规则

通过 `git rev-parse --is-inside-work-tree` 命令判断 skill 目录是否为 git 仓库：

```python
def _is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path), capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

相比检查 `.git` 子目录，此方法同时覆盖普通 clone 和 git worktree 场景（worktree 下 `.git` 是文件而非目录）。

## 数据层变更

### `store/skills_manager.py`

**新增 import：**

```python
import subprocess
```

**`SkillInfo` 新增字段：**

```python
@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    enabled: bool
    cli_id: str
    is_git: bool = False  # 新增
```

**新增 `_is_git_repo()` 辅助函数，`scan_skills()` 调用它检测 git：**

扫描每个 skill 时调用 `_is_git_repo(entry)`，将结果赋值给 `is_git`。

**新增 `git_pull_skill()` 函数：**

```python
def git_pull_skill(cli_id: str, skill_name: str, enabled: bool) -> tuple[bool, str]:
    """在 skill 目录执行 git pull，返回 (成功, 输出信息)。"""
```

路径构造复用 `load_skill_content()` 逻辑：

```python
skills_root = CLI_SKILLS_DIRS.get(cli_id)
base = skills_root if enabled else _disabled_dir(skills_root)
skill_dir = base / skill_name
```

通过 `subprocess.run(["git", "pull"], cwd=skill_dir, capture_output=True, text=True, timeout=30)` 执行。

异常处理：

| 场景 | 处理 |
|------|------|
| git 未安装 | 捕获 `FileNotFoundError`，返回 `(False, "未找到 git 命令")` |
| 超时 | `timeout=30`，超时返回 `(False, "git pull 超时（30s）")` |
| pull 失败 | git 返回码非 0，合并 stdout+stderr 返回 `(False, ...)` |
| 目录不存在 | 返回 `(False, "skill 目录不存在")` |

## UI 层变更

### `ui/skills_dialog.py`

**新增 import：**

```python
from PySide6.QtWidgets import QMessageBox
```

**`_rebuild_skill_list()` 每行布局变更：**

```
修改前：
  row_layout = QVBoxLayout(row_widget)
  [name_btn]

修改后：
  row_layout = QHBoxLayout(row_widget)
  [↑ icon_btn] [name_btn]
```

**图标按钮规格：**

| 属性 | 值 |
|------|-----|
| 文本 | `↑` |
| 固定宽度 | 24px |
| 字号 | 14px |
| 正常态颜色 | `#aaa` |
| hover 态颜色 | `#fff` |
| 置灰态颜色 | `#555` |
| cursor | `PointingHandCursor`（可用时） |

**状态逻辑：**

```
skill.is_git == True  → 图标正常，可点击
skill.is_git == False → 图标置灰，setEnabled(False)
```

**点击处理：**

点击图标 → `git_pull_skill()` → 使用 `QMessageBox.information()` / `QMessageBox.warning()` 弹出结果窗口

## 影响分析

- `SkillInfo.is_git` 默认值 `False`，`scan_skills()` 才设为 `True`，向后兼容
- `_is_git_repo()` 使用 `subprocess.run` 调用 git 命令，兼容普通 clone 和 worktree 场景
- `git_pull_skill()` 在非 git 目录不会被执行（UI 已禁用），因此不需要额外防御
- 无新增 Python 依赖（使用标准库 `subprocess`）
- 现有测试保持通过（`test_skills_manager.py` 需小幅更新以适配新字段）

## 测试

新增测试用例：

1. `test_git_pull_success` — mock git pull 成功，验证返回 `(True, ...)`
2. `test_git_pull_failure` — mock git pull 失败，验证返回 `(False, ...)`
3. `test_scan_skills_detects_git` — 在 tmp_path 创建带 `.git` 的 skill 目录，验证 `is_git=True`
4. `test_scan_skills_no_git` — 验证无 `.git` 时 `is_git=False`
