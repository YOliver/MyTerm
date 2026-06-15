# `_is_git_repo` 纯文件系统检查

> 移除 `_is_git_repo()` 中的 subprocess 调用，改为纯 `.git` 目录检查，消除 Skills 对话框启动延迟。

## 目标

`SkillsDialog` 打开时 `_populate_cli_list()` 调用 `scan_skills()`，后者对每个 skill 调用 `_is_git_repo()`。当前实现即使有 `.git` 前置检查，对存在 `.git` 目录的 skill 仍会启动 `git rev-parse` 子进程，造成累积延迟。

将 `_is_git_repo()` 改为纯文件系统检查：只判断 `skill/.git` 是否为目录，彻底删除 `subprocess` 调用。

## 改动

### `store/skills_manager.py`

**修改前：**

```python
def _is_git_repo(path: Path) -> bool:
    """通过 .git 目录/文件 + git rev-parse 判断目录是否为 git 仓库。"""
    git_path = path / ".git"
    if not git_path.exists():
        return False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path), capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

**修改后：**

```python
def _is_git_repo(path: Path) -> bool:
    """判断 skill 目录下是否有 .git 子目录（git clone 场景）。"""
    return (path / ".git").is_dir()
```

`import subprocess` 保留不动（`git_pull_skill()` 仍在使用）。

### `tests/test_skills_manager.py`

添加一个测试覆盖新增路径，修复/删除四个依赖 mock 的旧测试：

```python
# ── _is_git_repo（纯文件检查）──

def test_is_git_repo_has_dot_git_dir(tmp_path: Path):
    """skill 目录下有 .git 子目录 → True。"""
    (tmp_path / ".git").mkdir()
    from store.skills_manager import _is_git_repo
    assert _is_git_repo(tmp_path) is True


def test_is_git_repo_no_dot_git(tmp_path: Path):
    """无 .git 目录 → False。"""
    from store.skills_manager import _is_git_repo
    assert _is_git_repo(tmp_path) is False


def test_is_git_repo_dot_git_is_file(tmp_path: Path):
    """.git 是文件（worktree）→ False（不覆盖此场景）。"""
    (tmp_path / ".git").write_text("gitdir: /some/where/.git/worktrees/foo")
    from store.skills_manager import _is_git_repo
    assert _is_git_repo(tmp_path) is False
```

删除以下 4 个测试（不再适用）：
- `test_is_git_repo_true` — 依赖 mock `subprocess.run`
- `test_is_git_repo_false` — 依赖 mock `subprocess.run`
- `test_is_git_repo_no_git` — 依赖 mock `FileNotFoundError`
- `test_is_git_repo_timeout` — 依赖 mock `TimeoutExpired`

同时删除 `test_scan_skills_detects_git` 中的 subprocess mock，改为直接创建 `.git` 目录：

```python
def test_scan_skills_detects_git(tmp_path: Path, monkeypatch):
    """有 .git 时 is_git=True，无 .git 时 is_git=False。"""
    from store.skills_manager import CLI_SKILLS_DIRS

    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)

    (tmp_path / "skill-a").mkdir()
    (tmp_path / "skill-a" / ".git").mkdir()
    (tmp_path / "skill-a" / "SKILL.md").write_text(
        "---\nname: A\ndescription: Skill A\n---\n", encoding="utf-8",
    )

    (tmp_path / "skill-b").mkdir()
    (tmp_path / "skill-b" / "SKILL.md").write_text(
        "---\nname: B\ndescription: Skill B\n---\n", encoding="utf-8",
    )

    results = scan_skills("test_cli")
    assert len(results) == 2
    assert results[0].is_git is True
    assert results[1].is_git is False
```

## 影响

| 维度 | 变化 |
|------|------|
| O(1) 文件检查 | ✅ 全程无子进程 |
| `git clone` 场景 | ✅ 正常检测（`.git` 是目录） |
| git worktree 场景 | ❌ 不再支持（`.git` 是文件） |
| `_is_git_repo` 不再依赖 `subprocess` | ✅ `import subprocess` 仅 `git_pull_skill` 使用 |
