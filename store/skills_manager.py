"""各 CLI 全局 skills 目录扫描、启用/禁用、内容读取。

本模块无 Qt 依赖，所有函数均可脱离 UI 单测。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillInfo:
    """一个 skill 的元数据。

    字段：
    - ``name``：目录名，也是 skill 的唯一标识
    - ``description``：SKILL.md frontmatter 中的 description，解析失败时用首行兜底
    - ``enabled``：是否在 ``skills/`` 下（True）还是 ``skills-disabled/`` 下（False）
    - ``cli_id``：所属 CLI 的 ID，与 InstallerSpec.id 对齐
    - ``is_git``：skill 目录是否在 git 仓库中
    """
    name: str
    description: str
    enabled: bool
    cli_id: str
    is_git: bool = False


# 写死各 CLI 的 skills 根目录。CLI 未安装时目录可能不存在，scan_skills() 会返回空列表。
CLI_SKILLS_DIRS: dict[str, Path] = {
    "claude_code": Path.home() / ".claude" / "skills",
    "codebuddy": Path.home() / ".codebuddy" / "skills",
    "codex": Path.home() / ".codex" / "skills",
    "gemini": Path.home() / ".gemini" / "skills",
    "qwen_code": Path.home() / ".qwen" / "skills",
}

# 显示名映射（与 InstallerSpec.name 对齐，用于 UI 左侧列表）
CLI_DISPLAY_NAMES: dict[str, str] = {
    "claude_code": "Claude Code",
    "codebuddy": "CodeBuddy",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
    "qwen_code": "Qwen Code",
}


def _disabled_dir(skills_root: Path) -> Path:
    """给定 skills 根目录，返回对应的 skills-disabled 目录路径。"""
    parent = skills_root.parent
    name = skills_root.name
    return parent / f"{name}-disabled"


def _is_git_repo(path: Path) -> bool:
    """判断 skill 目录下是否有 .git 子目录（git clone 场景）。"""
    return (path / ".git").is_dir()


def _parse_skill_md(filepath: Path) -> tuple[str, str]:
    """从 SKILL.md 中提取 (name, description)。

    解析规则：
    1. 若文件以 ``---`` 开头，则尝试提取 YAML frontmatter 中的 ``name``/``description`` 字段
    2. frontmatter 解析失败或无 frontmatter 时，name 用父目录名，description 取文件首行非空文本
    3. 文件不存在时返回 ``(父目录名, "(无描述)")``
    """
    dir_name = filepath.parent.name
    try:
        text = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return dir_name, "(无描述)"

    lines = text.splitlines()
    name = dir_name
    description = ""

    # 尝试解析 YAML frontmatter（--- 开头，下一个 --- 结束）
    if lines and lines[0].strip() == "---":
        frontmatter: dict[str, str] = {}
        in_frontmatter = True
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                in_frontmatter = False
                break
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                frontmatter[key.strip()] = val.strip().strip('"').strip("'")
        if "name" in frontmatter:
            name = frontmatter["name"]
        if "description" in frontmatter:
            description = frontmatter["description"]

    # frontmatter 没给 description 时取正文首行非空文本。
    # 用 dash_count 计数 --- 分隔符：0=无 frontmatter，1=在 frontmatter 里，>=2=已到正文
    if not description:
        dash_count = 0
        for line in lines:
            if line.strip() == "---":
                dash_count += 1
                continue
            if dash_count >= 2 or dash_count == 0:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped[:120]  # 截断防止过长
                    break

    return name, description or "(无描述)"


def scan_skills(cli_id: str) -> list[SkillInfo]:
    """扫描指定 CLI 的全局 skills。

    同时扫描 ``skills/`` 和 ``skills-disabled/`` 两个目录，
    分别标记 enabled=True/False。目录不存在时返回空列表。

    每个 skill 目录下必须有 ``SKILL.md``（或以目录名兜底）。
    """
    skills_root = CLI_SKILLS_DIRS.get(cli_id)
    if skills_root is None:
        return []

    results: list[SkillInfo] = []

    for enabled, root in [(True, skills_root), (False, _disabled_dir(skills_root))]:
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            md_path = entry / "SKILL.md"
            name, description = _parse_skill_md(md_path)
            is_git = _is_git_repo(entry)
            results.append(SkillInfo(
                name=name,
                description=description,
                enabled=enabled,
                cli_id=cli_id,
                is_git=is_git,
            ))

    # 按 name 字典序排列
    results.sort(key=lambda s: s.name)
    return results


def set_skill_enabled(cli_id: str, skill_name: str, enabled: bool) -> bool:
    """启用或禁用一个 skill（目录移动）。

    - 启用：``skills-disabled/{name}/`` → ``skills/{name}/``
    - 禁用：``skills/{name}/`` → ``skills-disabled/{name}/``

    返回 True 表示操作成功；False 表示源目录不存在或移动失败。
    """
    skills_root = CLI_SKILLS_DIRS.get(cli_id)
    if skills_root is None:
        return False

    if enabled:
        src = _disabled_dir(skills_root) / skill_name
        dst = skills_root / skill_name
    else:
        src = skills_root / skill_name
        dst = _disabled_dir(skills_root) / skill_name

    if not src.is_dir():
        return False

    # 确保目标父目录存在
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    try:
        shutil.move(str(src), str(dst))
        return True
    except OSError:
        return False


def load_skill_content(cli_id: str, skill_name: str, enabled: bool) -> str:
    """读取指定 skill 的 SKILL.md 全文（供预览弹窗用）。"""
    skills_root = CLI_SKILLS_DIRS.get(cli_id)
    if skills_root is None:
        return ""
    base = skills_root if enabled else _disabled_dir(skills_root)
    md_path = base / skill_name / "SKILL.md"
    try:
        return md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def open_skills_dir(cli_id: str) -> None:
    """在资源管理器打开指定 CLI 的 skills 根目录。目录不存在时不操作。"""
    skills_root = CLI_SKILLS_DIRS.get(cli_id)
    if skills_root is None:
        return
    if skills_root.is_dir():
        os.startfile(str(skills_root))


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
