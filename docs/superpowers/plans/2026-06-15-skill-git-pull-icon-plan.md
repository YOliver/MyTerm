# Skills 列表 Git 更新图标 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Skills 浏览界面每个 skill 名称前增加 git pull 图标按钮

**Architecture:** 数据层新增 `_is_git_repo()` 检测和 `git_pull_skill()` 执行函数，UI 层在每行名称前插入图标按钮，TDD 驱动

**Tech Stack:** Python + PySide6 + pytest + subprocess (git)

---

### Task 1: SkillInfo 新增 `is_git` 字段 + `_is_git_repo()` 辅助函数

**Files:**
- Modify: `store/skills_manager.py:1-11,13-26`
- Test: `tests/test_skills_manager.py`

- [ ] **Step 1: 编写 `_is_git_repo` 测试**

```python
# ── _is_git_repo ──

def test_is_git_repo_true(tmp_path: Path, monkeypatch):
    """模拟 git rev-parse 返回 0（是 git 仓库）。"""
    from store.skills_manager import _is_git_repo, CLI_SKILLS_DIRS

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    import subprocess as _sp

    class FakeResult:
        returncode = 0

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(_sp, "run", fake_run)
    assert _is_git_repo(tmp_path) is True


def test_is_git_repo_false(tmp_path: Path, monkeypatch):
    """模拟 git rev-parse 返回非 0（不是 git 仓库）。"""
    from store.skills_manager import _is_git_repo
    import subprocess as _sp

    class FakeResult:
        returncode = 1

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(_sp, "run", fake_run)
    assert _is_git_repo(tmp_path) is False


def test_is_git_repo_no_git(tmp_path: Path, monkeypatch):
    """模拟 git 命令不存在（FileNotFoundError）。"""
    from store.skills_manager import _is_git_repo
    import subprocess as _sp

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(_sp, "run", fake_run)
    assert _is_git_repo(tmp_path) is False


def test_is_git_repo_timeout(tmp_path: Path, monkeypatch):
    """模拟 git 命令超时。"""
    from store.skills_manager import _is_git_repo
    import subprocess as _sp

    def fake_run(*args, **kwargs):
        raise _sp.TimeoutExpired(cmd="git", timeout=5)

    monkeypatch.setattr(_sp, "run", fake_run)
    assert _is_git_repo(tmp_path) is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_skills_manager.py::test_is_git_repo_true -v
```

预期：`AttributeError: module 'store.skills_manager' has no attribute '_is_git_repo'`

- [ ] **Step 3: 实现 `import subprocess`、`is_git` 字段、`_is_git_repo()`**

在 `store/skills_manager.py` 顶部新增 import：

```python
import subprocess
```

在 `SkillInfo` 新增字段：

```python
@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    enabled: bool
    cli_id: str
    is_git: bool = False
```

新增 `_is_git_repo()` 函数（插入在 `_disabled_dir` 之后）：

```python
def _is_git_repo(path: Path) -> bool:
    """通过 git rev-parse 判断目录是否在 git 仓库中。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path), capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_skills_manager.py::test_is_git_repo_true tests/test_skills_manager.py::test_is_git_repo_false tests/test_skills_manager.py::test_is_git_repo_no_git tests/test_skills_manager.py::test_is_git_repo_timeout -v
```

预期：4 passed

- [ ] **Step 5: 提交**

```bash
git add store/skills_manager.py tests/test_skills_manager.py
git commit -m "feat: SkillInfo 新增 is_git 字段，添加 _is_git_repo() 检测函数"
```

---

### Task 2: `scan_skills()` 集成 git 检测

**Files:**
- Modify: `store/skills_manager.py:107-142`
- Test: `tests/test_skills_manager.py`

- [ ] **Step 1: 编写 `scan_skills` git 检测测试**

```python
def test_scan_skills_detects_git(tmp_path: Path, monkeypatch):
    """有 .git 目录时 is_git=True，无 .git 时 is_git=False。"""
    from store.skills_manager import CLI_SKILLS_DIRS
    import subprocess as _sp

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)

    # skill-a 有 git
    (tmp_path / "skill-a").mkdir()
    (tmp_path / "skill-a" / "SKILL.md").write_text(
        "---\nname: A\ndescription: Skill A\n---\n", encoding="utf-8",
    )
    # skill-b 无 git
    (tmp_path / "skill-b").mkdir()
    (tmp_path / "skill-b" / "SKILL.md").write_text(
        "---\nname: B\ndescription: Skill B\n---\n", encoding="utf-8",
    )

    call_count = [0]

    def fake_run(*args, **kwargs):
        call_count[0] += 1
        class R:
            pass
        # 第一个调用（skill-a）返回 0，第二个（skill-b）返回 1
        r = R()
        r.returncode = 0 if call_count[0] == 1 else 1
        return r

    monkeypatch.setattr(_sp, "run", fake_run)

    results = scan_skills("test_cli")
    assert len(results) == 2
    assert results[0].is_git is True
    assert results[1].is_git is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_skills_manager.py::test_scan_skills_detects_git -v
```

预期：FAIL — `assert True is False`（Task 1 已添加 `is_git` 默认值 `False`，但 `scan_skills()` 尚未调用 `_is_git_repo()`，所以返回默认值 `False`，对 skill-a 的断言 `is True` 会失败）

- [ ] **Step 3: 在 `scan_skills()` 中集成 `_is_git_repo()`**

修改 `scan_skills()` 中 `SkillInfo` 构造处（第 133-138 行）：

```python
            is_git = _is_git_repo(entry)
            results.append(SkillInfo(
                name=name,
                description=description,
                enabled=enabled,
                cli_id=cli_id,
                is_git=is_git,
            ))
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_skills_manager.py::test_scan_skills_detects_git -v
```

预期：PASS

- [ ] **Step 5: 确认已有测试不受影响**

```bash
python -m pytest tests/test_skills_manager.py -v
```

预期：全部 passing

- [ ] **Step 6: 提交**

```bash
git add store/skills_manager.py tests/test_skills_manager.py
git commit -m "feat: scan_skills 集成 git 仓库检测"
```

---

### Task 3: 实现 `git_pull_skill()` 函数

**Files:**
- Modify: `store/skills_manager.py`（在 `open_skills_dir` 之后新增）
- Test: `tests/test_skills_manager.py`

- [ ] **Step 1: 编写 `git_pull_skill` 测试**

```python
# ── git_pull_skill ──

def test_git_pull_success(tmp_path: Path, monkeypatch):
    """模拟 git pull 成功。"""
    from store.skills_manager import git_pull_skill, CLI_SKILLS_DIRS
    import subprocess as _sp

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "s").mkdir()

    class FakeResult:
        returncode = 0
        stdout = "Already up to date.\n"
        stderr = ""

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(_sp, "run", fake_run)
    ok, msg = git_pull_skill("test_cli", "s", enabled=True)
    assert ok is True
    assert "up to date" in msg


def test_git_pull_failure(tmp_path: Path, monkeypatch):
    """模拟 git pull 失败。"""
    from store.skills_manager import git_pull_skill, CLI_SKILLS_DIRS
    import subprocess as _sp

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "s").mkdir()

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "fatal: not a git repository\n"

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(_sp, "run", fake_run)
    ok, msg = git_pull_skill("test_cli", "s", enabled=True)
    assert ok is False
    assert "fatal" in msg


def test_git_pull_no_git_cmd(tmp_path: Path, monkeypatch):
    """模拟 git 命令不存在。"""
    from store.skills_manager import git_pull_skill, CLI_SKILLS_DIRS
    import subprocess as _sp

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "s").mkdir()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(_sp, "run", fake_run)
    ok, msg = git_pull_skill("test_cli", "s", enabled=True)
    assert ok is False
    assert "未找到 git" in msg


def test_git_pull_skill_dir_missing(tmp_path: Path, monkeypatch):
    """skill 目录不存在时返回失败。"""
    from store.skills_manager import git_pull_skill, CLI_SKILLS_DIRS

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    # 不创建目录
    ok, msg = git_pull_skill("test_cli", "ghost", enabled=True)
    assert ok is False
    assert "不存在" in msg


def test_git_pull_unknown_cli():
    """CLI 不存在时返回失败。"""
    from store.skills_manager import git_pull_skill

    ok, msg = git_pull_skill("fake", "x", enabled=True)
    assert ok is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_skills_manager.py::test_git_pull_success -v
```

预期：`ImportError: cannot import name 'git_pull_skill'`

- [ ] **Step 3: 实现 `git_pull_skill()`**

在 `store/skills_manager.py` 末尾新增（在 `open_skills_dir` 之后）：

```python
def git_pull_skill(cli_id: str, skill_name: str, enabled: bool) -> tuple[bool, str]:
    """在 skill 目录执行 git pull，返回 (成功, 输出信息)。"""
    skills_root = CLI_SKILLS_DIRS.get(cli_id)
    if skills_root is None:
        return False, "未知的 CLI"
    base = skills_root if enabled else _disabled_dir(skills_root)
    skill_dir = base / skill_name
    if not skill_dir.is_dir():
        return False, "skill 目录不存在"
    try:
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        return False, "未找到 git 命令"
    except subprocess.TimeoutExpired:
        return False, "git pull 超时（30s）"
    if result.returncode != 0:
        return False, (result.stdout + result.stderr).strip() or "git pull 失败"
    return True, (result.stdout or "OK").strip()
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_skills_manager.py::test_git_pull_success tests/test_skills_manager.py::test_git_pull_failure tests/test_skills_manager.py::test_git_pull_no_git_cmd tests/test_skills_manager.py::test_git_pull_skill_dir_missing tests/test_skills_manager.py::test_git_pull_unknown_cli -v
```

预期：5 passed

- [ ] **Step 5: 提交**

```bash
git add store/skills_manager.py tests/test_skills_manager.py
git commit -m "feat: 实现 git_pull_skill() 函数及单测"
```

---

### Task 4: UI 层添加更新图标按钮

**Files:**
- Modify: `ui/skills_dialog.py:1-19,87-301`

- [ ] **Step 1: 新增 import**

在 `ui/skills_dialog.py` 顶部新增 `QMessageBox` import：

```python
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,   # 新增
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
```

在 `store.skills_manager` import 中新增 `git_pull_skill`：

```python
from store.skills_manager import (
    CLI_DISPLAY_NAMES,
    CLI_SKILLS_DIRS,
    SkillInfo,
    git_pull_skill,   # 新增
    load_skill_content,
    open_skills_dir,
    scan_skills,
)
```

- [ ] **Step 2: 修改 `_rebuild_skill_list()` 每行布局**

将每行从 `QHBoxLayout` 替代 `QVBoxLayout`，在名称按钮前插入图标按钮。修改第 235-250 行：

```python
        for skill in skills:
            row_widget = QWidget()
            row_widget.setStyleSheet("QWidget { background: #1e1e1e; }")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 3, 4, 3)
            row_layout.setSpacing(4)

            # 更新图标按钮
            icon_btn = QPushButton("↑", row_widget)
            icon_btn.setFixedWidth(24)
            icon_btn.setFlat(True)
            if skill.is_git:
                icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                icon_btn.setStyleSheet(
                    "QPushButton { color: #aaa; font-size: 14px; background: transparent;"
                    " border: none; padding: 0; }"
                    "QPushButton:hover { color: #fff; }"
                )
                icon_btn.clicked.connect(
                    self._make_pull_handler(skill)
                )
            else:
                icon_btn.setEnabled(False)
                icon_btn.setStyleSheet(
                    "QPushButton { color: #555; font-size: 14px; background: transparent;"
                    " border: none; padding: 0; }"
                )

            row_layout.addWidget(icon_btn)

            name_btn = QPushButton(skill.name, row_widget)
            name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            name_btn.setStyleSheet(_SKILL_BTN_BASE)
            name_btn.clicked.connect(
                lambda _checked, btn=name_btn, n=skill.name: self._select_skill(btn, n)
            )
            row_layout.addWidget(name_btn, 1)

            self._skill_layout.addWidget(row_widget)
```

- [ ] **Step 3: 新增 `_make_pull_handler()` 方法和 `_on_pull_skill()` 方法**

在 `SkillsDialog` 类中新增两个方法（放在 `_on_preview` 之后）：

```python
    def _make_pull_handler(self, skill: SkillInfo):
        """返回一个闭包，用于点击图标时触发 git pull。"""
        def handler(_checked: bool | None = None) -> None:
            self._on_pull_skill(skill)
        return handler

    def _on_pull_skill(self, skill: SkillInfo) -> None:
        """执行 git pull 并弹出结果提示。"""
        ok, msg = git_pull_skill(skill.cli_id, skill.name, skill.enabled)
        if ok:
            QMessageBox.information(self, "git pull 成功", msg)
        else:
            QMessageBox.warning(self, "git pull 失败", msg)
```

- [ ] **Step 4: 提交**

```bash
git add ui/skills_dialog.py
git commit -m "feat: skills 列表每行添加 git pull 更新图标按钮"
```

---

### Task 5: 运行全量测试 + 自检

- [ ] **Step 1: 运行全量测试**

```bash
python -m pytest tests/ -v
```

预期：全部通过

- [ ] **Step 2: 确认已有测试均通过**

特别关注 `test_skills_manager.py` 中已有的 `scan_skills` 和 `SkillInfo` 相关测试，确保 `is_git` 默认值不影响现有断言。

- [ ] **Step 3: 提交（如有修正）**

```bash
git add -A && git commit -m "test: 确认全量测试通过"
```

---

### Task 6: 运行 UI 手动验证

- [ ] **Step 1: 启动 MyTerm，打开 Skills 菜单**

- [ ] **Step 2: 验证图标展示**
  - 有 git 的 skill 应显示亮色 `↑`，hover 变白
  - 无 git 的 skill 应显示灰色 `↑`，hover 不变

- [ ] **Step 3: 验证点击行为**
  - 点击有 git skill 的图标 → 执行 git pull → 弹出成功/失败提示
  - 无 git skill 的图标不可点击

- [ ] **Step 4: 切换到其他 CLI 确认列表正常渲染**
