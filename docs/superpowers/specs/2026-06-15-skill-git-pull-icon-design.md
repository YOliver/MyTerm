# Skills 列表 Git 更新图标

> 在 Skills 浏览界面每个 skill 名称前添加更新箭头图标，git 管理的 skill 可一键 pull，非 git 管理的图标置灰。

## 目标

在 `SkillsDialog` 右侧 skill 列表的每一行名称前增加一个更新箭头图标：

- git 管理的 skill：图标可点击，点击后执行 `git pull`，弹窗提示成功/失败
- 非 git 管理的 skill：图标置灰，不可点击

## 检测规则

在 skill 目录下检查是否包含 `.git` 子目录：

```
.codebuddy/skills/some-skill/.git  → 是 git 仓库
.codebuddy/skills/other-skill/     → 不是 git 仓库（无 .git）
```

仅检查 skill 目录本身是否是 git 仓库根目录，不递归检查父目录。覆盖最常见场景（`git clone` 到 skills 目录）。

## 数据层变更

### `store/skills_manager.py`

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

**`scan_skills()` 增加 git 检测：**

扫描每个 skill 时检查 `entry / ".git"` 是否为目录，设为 `is_git` 的值。

**新增 `git_pull_skill()` 函数：**

```python
def git_pull_skill(cli_id: str, skill_name: str, enabled: bool) -> tuple[bool, str]:
    """在 skill 目录执行 git pull，返回 (成功, 输出信息)。"""
```

拼接 skill 目录路径，执行 `git pull`，收集 stdout/stderr，返回结果。

## UI 层变更

### `ui/skills_dialog.py`

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
- `git_pull_skill()` 在非 git 目录不会被执行（UI 已禁用），因此不需要额外防御
- 无新增 Python 依赖（使用标准库 `subprocess`）
- 现有测试保持通过（`test_skills_manager.py` 需小幅更新以适配新字段）

## 测试

新增测试用例：

1. `test_git_pull_success` — mock git pull 成功，验证返回 `(True, ...)`
2. `test_git_pull_failure` — mock git pull 失败，验证返回 `(False, ...)`
3. `test_scan_skills_detects_git` — 在 tmp_path 创建带 `.git` 的 skill 目录，验证 `is_git=True`
4. `test_scan_skills_no_git` — 验证无 `.git` 时 `is_git=False`
