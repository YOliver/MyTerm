"""store/skills_manager.py 单测。

全部用 tmp_path 隔离文件系统，不依赖真实 ~/.claude/skills/ 目录。
"""
import pytest
from pathlib import Path

from store.skills_manager import (
    SkillInfo,
    _disabled_dir,
    _parse_skill_md,
    scan_skills,
    set_skill_enabled,
    load_skill_content,
    CLI_SKILLS_DIRS,
)


# ── _parse_skill_md ──

def test_parse_skill_md_with_frontmatter(tmp_path: Path):
    d = tmp_path / "brainstorming"
    d.mkdir()
    md = d / "SKILL.md"
    md.write_text(
        "---\n"
        'name: brainstorming\n'
        'description: "You MUST use this before any creative work"\n'
        "---\n"
        "# Brainstorming\n"
        "Help turn ideas into designs.\n",
        encoding="utf-8",
    )
    name, desc = _parse_skill_md(md)
    assert name == "brainstorming"
    assert "MUST use this" in desc


def test_parse_skill_md_no_frontmatter(tmp_path: Path):
    d = tmp_path / "myskill"
    d.mkdir()
    md = d / "SKILL.md"
    md.write_text("# My Skill\n\nThis is my skill.\n", encoding="utf-8")
    name, desc = _parse_skill_md(md)
    assert name == "myskill"
    assert desc != "(无描述)"


def test_parse_skill_md_missing_file(tmp_path: Path):
    d = tmp_path / "orphan"
    d.mkdir()
    md = d / "SKILL.md"  # 不创建文件
    name, desc = _parse_skill_md(md)
    assert name == "orphan"
    assert desc == "(无描述)"


def test_parse_skill_md_empty_body(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    md = d / "SKILL.md"
    md.write_text(
        "---\n"
        'name: empty-skill\n'
        "---\n",
        encoding="utf-8",
    )
    name, desc = _parse_skill_md(md)
    assert name == "empty-skill"
    assert desc == "(无描述)"


def test_parse_skill_md_frontmatter_no_description(tmp_path: Path):
    """有 frontmatter 但无 description 字段：应取正文首行，不取 frontmatter 内容。"""
    d = tmp_path / "nosdesc"
    d.mkdir()
    md = d / "SKILL.md"
    md.write_text(
        "---\n"
        "name: nosdesc\n"
        "---\n"
        "This is the real description.\n",
        encoding="utf-8",
    )
    name, desc = _parse_skill_md(md)
    assert name == "nosdesc"
    assert desc == "This is the real description."


# ── scan_skills ──

def test_scan_empty_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    results = scan_skills("test_cli")
    assert results == []


def test_scan_skills_enabled_only(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "skill-a").mkdir()
    (tmp_path / "skill-a" / "SKILL.md").write_text(
        "---\nname: A\ndescription: Skill A\n---\n", encoding="utf-8",
    )
    (tmp_path / "skill-b").mkdir()
    (tmp_path / "skill-b" / "SKILL.md").write_text(
        "---\nname: B\ndescription: Skill B\n---\n", encoding="utf-8",
    )
    results = scan_skills("test_cli")
    assert len(results) == 2
    assert all(r.enabled for r in results)
    assert results[0].name == "A"
    assert results[1].name == "B"


def test_scan_skills_with_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    # enabled
    (tmp_path / "active").mkdir()
    (tmp_path / "active" / "SKILL.md").write_text(
        "---\nname: active\ndescription: on\n---\n", encoding="utf-8",
    )
    # disabled
    disabled_dir = _disabled_dir(tmp_path)
    disabled_dir.mkdir()
    (disabled_dir / "inactive").mkdir()
    (disabled_dir / "inactive" / "SKILL.md").write_text(
        "---\nname: inactive\ndescription: off\n---\n", encoding="utf-8",
    )
    results = scan_skills("test_cli")
    assert len(results) == 2
    enabled = [r for r in results if r.enabled]
    disabled = [r for r in results if not r.enabled]
    assert len(enabled) == 1
    assert len(disabled) == 1
    assert enabled[0].name == "active"
    assert disabled[0].name == "inactive"


def test_scan_skills_nonexistent_cli():
    results = scan_skills("nonexistent")
    assert results == []


# ── set_skill_enabled ──

def test_disable_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "myskill").mkdir()
    (tmp_path / "myskill" / "SKILL.md").write_text(
        "---\nname: myskill\n---\n", encoding="utf-8",
    )
    assert set_skill_enabled("test_cli", "myskill", False)
    assert not (tmp_path / "myskill").exists()
    assert (_disabled_dir(tmp_path) / "myskill").is_dir()


def test_enable_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    disabled_dir = _disabled_dir(tmp_path)
    disabled_dir.mkdir(parents=True)
    (disabled_dir / "myskill").mkdir()
    (disabled_dir / "myskill" / "SKILL.md").write_text(
        "---\nname: myskill\n---\n", encoding="utf-8",
    )
    assert set_skill_enabled("test_cli", "myskill", True)
    assert not (disabled_dir / "myskill").exists()
    assert (tmp_path / "myskill").is_dir()


def test_set_skill_enabled_nonexistent_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    assert not set_skill_enabled("test_cli", "ghost", False)


def test_set_skill_enabled_unknown_cli():
    assert not set_skill_enabled("fake", "x", True)


# ── load_skill_content ──

def test_load_skill_content(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "SKILL.md").write_text("hello world", encoding="utf-8")
    content = load_skill_content("test_cli", "s", enabled=True)
    assert content == "hello world"


def test_load_skill_content_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setitem(CLI_SKILLS_DIRS, "test_cli", tmp_path)
    dd = _disabled_dir(tmp_path)
    dd.mkdir(parents=True)
    (dd / "s").mkdir()
    (dd / "s" / "SKILL.md").write_text("disabled content", encoding="utf-8")
    content = load_skill_content("test_cli", "s", enabled=False)
    assert content == "disabled content"


# ── _disabled_dir ──

def test_disabled_dir_naming():
    assert _disabled_dir(Path("/home/user/.claude/skills")) == Path("/home/user/.claude/skills-disabled")


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
