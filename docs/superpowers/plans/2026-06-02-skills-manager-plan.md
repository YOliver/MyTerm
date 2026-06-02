# Skills 管理器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Skills 从"设置"子菜单提升为顶级菜单，提供按 CLI 分组浏览/启用禁用/预览 SKILL.md 的对话框。

**Architecture:** 遵循现有三层模式 — `store/skills_manager.py`（纯逻辑，无 Qt 依赖）、`ui/skills_dialog.py`（QDialog + QListWidget + 动态 checkbox）、`ui/main_window.py`（菜单注册修改）。启用/禁用通过 `shutil.move` 在 `skills/` 与 `skills-disabled/` 目录间移动实现。

**Tech Stack:** Python 3.10+, PySide6, pathlib, shutil, yaml (SKILL.md frontmatter 解析)

---

### Task 1: 纯逻辑层 — store/skills_manager.py

**Files:**
- Create: `store/skills_manager.py`

- [ ] **Step 1: 实现 CLI 元数据与 SkillInfo**

```python
"""各 CLI 全局 skills 目录扫描、启用/禁用、内容读取。

本模块无 Qt 依赖，所有函数均可脱离 UI 单测。
"""
from __future__ import annotations

import os
import shutil
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
    """
    name: str
    description: str
    enabled: bool
    cli_id: str


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
```

- [ ] **Step 2: 实现 SKILL.md frontmatter 解析**

在 `store/skills_manager.py` 中继续追加：

```python
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

    # frontmatter 没给 description 时取正文首行非空文本
    if not description:
        in_body = False
        for line in lines:
            if line.strip() == "---":
                in_body = True
                continue
            if in_body or lines[0].strip() != "---":
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    description = stripped[:120]  # 截断防止过长
                    break

    return name, description or "(无描述)"
```

- [ ] **Step 3: 实现 scan_skills()**

```python
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
            results.append(SkillInfo(
                name=name,
                description=description,
                enabled=enabled,
                cli_id=cli_id,
            ))

    # 按 name 字典序排列
    results.sort(key=lambda s: s.name)
    return results
```

- [ ] **Step 4: 实现 set_skill_enabled()**

```python
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
```

- [ ] **Step 5: 实现 load_skill_content() 和 open_skills_dir()**

```python
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
```

- [ ] **Step 6: 验证 store 模块可 import**

```bash
python -c "from store.skills_manager import SkillInfo, CLI_SKILLS_DIRS, scan_skills, set_skill_enabled, load_skill_content, open_skills_dir; print('skills_manager OK')"
```

Expected: `skills_manager OK`

- [ ] **Step 7: 提交**

```bash
git add store/skills_manager.py
git commit -m "feat: add skills_manager — 扫描/启用禁用/读取 skill 纯逻辑层"
```

---

### Task 2: 纯逻辑层单测 — tests/test_skills_manager.py

**Files:**
- Create: `tests/test_skills_manager.py`

- [ ] **Step 1: 写测试**

```python
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
```

- [ ] **Step 2: 运行测试验证全部 FAIL**

```bash
pytest tests/test_skills_manager.py -v
```

Expected: 14 failed（模块尚未创建）

- [ ] **Step 3: 运行测试验证全部 PASS**

```bash
pytest tests/test_skills_manager.py -v
```

Expected: 14 passed

- [ ] **Step 4: 提交**

```bash
git add tests/test_skills_manager.py
git commit -m "test: add skills_manager 单测（14 条）"
```

---

### Task 3: UI 对话框 — ui/skills_dialog.py

**Files:**
- Create: `ui/skills_dialog.py`

- [ ] **Step 1: 实现 SkillPreviewDialog**

```python
"""Skills 管理对话框：按 CLI 分组浏览、启用/禁用、预览 SKILL.md。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from store.skills_manager import (
    CLI_DISPLAY_NAMES,
    CLI_SKILLS_DIRS,
    SkillInfo,
    load_skill_content,
    open_skills_dir,
    scan_skills,
    set_skill_enabled,
)

_DIALOG_STYLE = (
    "QDialog { background: #1e1e1e; }"
    "QListWidget {"
    "  background: #252526; color: #ccc;"
    "  border: 1px solid #3a3a3a; border-radius: 4px;"
    "  font-family: Consolas; font-size: 12px;"
    "}"
    "QListWidget::item { padding: 6px 10px; }"
    "QListWidget::item:selected { background: #094771; color: #fff; }"
    "QListWidget::item:hover { background: #2a2d2e; }"
    "QScrollArea { background: #1e1e1e; border: 1px solid #3a3a3a; border-radius: 4px; }"
    "QCheckBox {"
    "  color: #ccc; font-family: Consolas; font-size: 12px; spacing: 8px;"
    "}"
    "QCheckBox::indicator { width: 16px; height: 16px; }"
    "QCheckBox::indicator:unchecked {"
    "  background: #3a3a3a; border: 1px solid #555; border-radius: 3px;"
    "}"
    "QCheckBox::indicator:checked {"
    "  background: #0e639c; border: 1px solid #1177bb; border-radius: 3px;"
    "}"
    "QLabel { color: #aaa; font-family: Consolas; font-size: 11px; }"
    "QPushButton {"
    "  font-size: 12px; padding: 6px 16px;"
    "  background: #444; color: #ccc; border: none; border-radius: 3px;"
    "}"
    "QPushButton:hover { background: #555; }"
)


class SkillPreviewDialog(QDialog):
    """SKILL.md 全文预览弹窗。"""

    def __init__(self, skill_name: str, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"预览 — {skill_name}")
        self.resize(640, 480)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        viewer = QTextEdit(self)
        viewer.setReadOnly(True)
        viewer.setPlainText(content)
        viewer.setStyleSheet(
            "QTextEdit {"
            "  background: #1e1e1e; color: #ccc;"
            "  font-family: Consolas; font-size: 13px;"
            "  border: 1px solid #3a3a3a; border-radius: 4px;"
            "}"
        )
        layout.addWidget(viewer, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
```

- [ ] **Step 2: 实现 SkillsDialog 主体**

在 `ui/skills_dialog.py` 中继续追加：

```python
class SkillsDialog(QDialog):
    """Skills 管理主对话框：左侧 CLI 列表，右侧 skill 清单 + 操作按钮。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skills 管理")
        self.resize(800, 520)
        self.setStyleSheet(_DIALOG_STYLE)

        self._cli_ids = list(CLI_SKILLS_DIRS.keys())
        self._current_cli: str | None = None
        # 缓存每个 CLI 的 skills 列表，checkbox 状态变更后同步更新
        self._skills_cache: dict[str, list[SkillInfo]] = {}

        body = QHBoxLayout(self)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(10)

        # ── 左侧 CLI 列表 ──
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)

        cli_label = QLabel("CLI 工具", self)
        left_layout.addWidget(cli_label)

        self._cli_list = QListWidget(self)
        self._cli_list.setFixedWidth(180)
        self._cli_list.currentRowChanged.connect(self._on_cli_selected)
        left_layout.addWidget(self._cli_list, 1)
        body.addLayout(left_layout)

        # ── 右侧 skills 区域 ──
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        self._right_title = QLabel("", self)
        self._right_title.setStyleSheet("QLabel { color: #ccc; font-size: 13px; font-weight: bold; }")
        right_layout.addWidget(self._right_title)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._skill_container = QWidget()
        self._skill_layout = QVBoxLayout(self._skill_container)
        self._skill_layout.setContentsMargins(8, 8, 8, 8)
        self._skill_layout.setSpacing(4)
        self._skill_layout.addStretch()
        self._scroll.setWidget(self._skill_container)
        right_layout.addWidget(self._scroll, 1)

        # 空状态占位
        self._empty_label = QLabel("", self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("QLabel { color: #666; font-size: 14px; padding: 40px; }")
        self._empty_label.hide()
        right_layout.addWidget(self._empty_label)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._open_dir_btn = QPushButton("打开 Skills 目录", self)
        self._open_dir_btn.clicked.connect(self._on_open_dir)
        btn_row.addWidget(self._open_dir_btn)

        self._preview_btn = QPushButton("查看 SKILL.md", self)
        self._preview_btn.clicked.connect(self._on_preview)
        btn_row.addWidget(self._preview_btn)

        btn_row.addStretch()
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        right_layout.addLayout(btn_row)

        body.addLayout(right_layout, 1)

        # 填充左侧 CLI 列表
        self._populate_cli_list()
```

- [ ] **Step 3: 实现 SkillsDialog 方法**

在 `SkillsDialog` 类中追加：

```python
    def _populate_cli_list(self) -> None:
        """扫描所有 CLI 并填充左侧列表。"""
        self._cli_list.clear()
        for cli_id in self._cli_ids:
            skills = scan_skills(cli_id)
            self._skills_cache[cli_id] = skills
            display = CLI_DISPLAY_NAMES.get(cli_id, cli_id)
            count = len(skills)
            # 数量 0 的灰色显示
            text = f"{display}  ({count})"
            item = QListWidgetItem(text)
            if count == 0:
                item.setForeground(Qt.GlobalColor.gray)
            self._cli_list.addItem(item)
        if self._cli_list.count() > 0:
            self._cli_list.setCurrentRow(0)

    def _on_cli_selected(self, row: int) -> None:
        """切换 CLI 时刷新右侧 skill 列表。"""
        if row < 0 or row >= len(self._cli_ids):
            return
        cli_id = self._cli_ids[row]
        self._current_cli = cli_id
        self._selected_skill_name = None  # 切换 CLI 时清空选中
        skills = self._skills_cache.get(cli_id, [])
        self._rebuild_skill_list(skills)

    def _rebuild_skill_list(self, skills: list[SkillInfo]) -> None:
        """重新构建右侧 skill checkbox 列表。"""
        # 清空旧 widgets
        while self._skill_layout.count() > 0:
            item = self._skill_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        display = CLI_DISPLAY_NAMES.get(self._current_cli, self._current_cli or "")
        count = len(skills)
        self._right_title.setText(f"{display} 的 Skills（{count} 个）")

        self._scroll.show()
        self._empty_label.hide()

        if not skills:
            self._scroll.hide()
            roots = CLI_SKILLS_DIRS.get(self._current_cli or "", Path(""))
            if roots.is_dir():
                self._empty_label.setText("该 CLI 下暂无全局 skills\n\n你可以将 skill 目录放入对应的 skills 文件夹")
            else:
                self._empty_label.setText("该 CLI 未安装或无全局 skills 目录")
            self._empty_label.show()
            return

        for skill in skills:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 3, 4, 3)
            row_layout.setSpacing(1)

            cb = QCheckBox(skill.name, row_widget)
            cb.setChecked(skill.enabled)
            # 回调时用默认参数捕获当前值，避免闭包延迟绑定
            cb.toggled.connect(
                lambda checked, s=skill: self._on_toggle(s, checked)
            )
            # 记录最后一次点击的 skill 名（用于预览按钮），只存名称避免 stale reference
            cb.clicked.connect(
                lambda _checked, n=skill.name: setattr(self, "_selected_skill_name", n)
            )

            desc_label = QLabel(f"  {skill.description}", row_widget)
            desc_label.setStyleSheet("QLabel { color: #888; font-size: 11px; }")

            row_layout.addWidget(cb)
            row_layout.addWidget(desc_label)
            self._skill_layout.addWidget(row_widget)

        self._skill_layout.addStretch()

    def _on_toggle(self, skill: SkillInfo, checked: bool) -> None:
        """checkbox 切换时移动目录。"""
        cli_id = skill.cli_id
        ok = set_skill_enabled(cli_id, skill.name, checked)
        if not ok:
            display = CLI_DISPLAY_NAMES.get(cli_id, cli_id)
            action = "启用" if checked else "禁用"
            QMessageBox.warning(
                self, "操作失败",
                f"{action} skill \"{skill.name}\" 失败。\n\n"
                f"请检查 {display} 的 skills 目录权限。",
            )
            # 刷新回真实状态
            self._refresh_current()
            return
        # 更新缓存
        self._skills_cache[cli_id] = scan_skills(cli_id)
        # 更新左侧计数
        self._update_cli_count(cli_id)

    def _refresh_current(self) -> None:
        """重新扫描当前 CLI 并刷新右侧列表。"""
        if self._current_cli is None:
            return
        skills = scan_skills(self._current_cli)
        self._skills_cache[self._current_cli] = skills
        self._rebuild_skill_list(skills)

    def _update_cli_count(self, cli_id: str) -> None:
        """更新左侧列表中某个 CLI 的技能计数。"""
        try:
            idx = self._cli_ids.index(cli_id)
        except ValueError:
            return
        skills = self._skills_cache.get(cli_id, [])
        display = CLI_DISPLAY_NAMES.get(cli_id, cli_id)
        text = f"{display}  ({len(skills)})"
        item = self._cli_list.item(idx)
        if item:
            item.setText(text)
            if len(skills) == 0:
                item.setForeground(Qt.GlobalColor.gray)

    def _on_open_dir(self) -> None:
        """打开当前选中 CLI 的 skills 目录。"""
        if self._current_cli is None:
            return
        open_skills_dir(self._current_cli)

    def _on_preview(self) -> None:
        """预览当前选中 skill 的 SKILL.md 全文。

        优先取用户最后一次点击 checkbox 的 skill 名（``_selected_skill_name``），
        fallback 到列表第一个。从缓存中获取最新的 enabled 状态，而非闭包中
        可能过期的 SkillInfo 引用。
        """
        if self._current_cli is None:
            return
        skills = self._skills_cache.get(self._current_cli, [])
        if not skills:
            return
        skill: SkillInfo | None = None
        if self._selected_skill_name is not None:
            for s in skills:
                if s.name == self._selected_skill_name:
                    skill = s
                    break
        if skill is None:
            skill = skills[0]
        content = load_skill_content(self._current_cli, skill.name, skill.enabled)
        SkillPreviewDialog(skill.name, content, self).exec()
```

在 `__init__` 中追加一行（放在 `self._skills_cache: dict[str, list[SkillInfo]] = {}` 之后）：

```python
        self._selected_skill_name: str | None = None
```

- [ ] **Step 5: 验证 dialog 模块可 import**

```bash
python -c "from ui.skills_dialog import SkillsDialog, SkillPreviewDialog; print('skills_dialog OK')"
```

Expected: `skills_dialog OK`

- [ ] **Step 6: 提交**

```bash
git add ui/skills_dialog.py
git commit -m "feat: add Skills 管理对话框（浏览/启用禁用/预览）"
```

---

### Task 4: 菜单注册修改 — ui/main_window.py

**Files:**
- Modify: `ui/main_window.py`

- [ ] **Step 1: 将 Skills 从设置子菜单提升为顶级菜单**

在 `_build_menubar` 中：

**删除** skills action 在 settings_menu 中的注册（第 318-319 行）：
```python
        skills_action = settings_menu.addAction("skills")
        skills_action.triggered.connect(self._on_open_skills)
```

**在设置菜单之后、日志菜单之前，插入顶级 Skills 菜单，内含一个 action**。

完整修改后的 `_build_menubar` 为：

```python
    def _build_menubar(self):
        """主窗口顶部标准 QMenuBar，深色主题与 topbar 对齐。"""
        menubar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background: #2d2d2d; color: #ccc; }"
            "QMenuBar::item { padding: 4px 12px; background: transparent; }"
            "QMenuBar::item:selected { background: #094771; }"
            "QMenu { background: #252526; color: #ccc; border: 1px solid #555; }"
            "QMenu::item { padding: 6px 24px; }"
            "QMenu::item:selected { background: #094771; }"
        )
        env_menu = menubar.addMenu("环境")
        check_action = env_menu.addAction("检测依赖")
        check_action.triggered.connect(self._on_check_env)

        settings_menu = menubar.addMenu("设置")
        shell_action = settings_menu.addAction("AI CLI 配置...")
        shell_action.triggered.connect(self._on_open_settings)
        cli_install_action = settings_menu.addAction("CLI 安装")
        cli_install_action.triggered.connect(self._on_open_cli_install)

        skills_menu = menubar.addMenu("Skills")
        manage_action = skills_menu.addAction("管理 Skills")
        manage_action.triggered.connect(self._on_open_skills_dialog)

        log_menu = menubar.addMenu("日志")
        open_log_action = log_menu.addAction("打开日志目录")
        open_log_action.triggered.connect(self._on_open_log_dir)

        help_menu = menubar.addMenu("帮助")
        welcome_action = help_menu.addAction("欢迎")
        welcome_action.triggered.connect(self._on_help_welcome)
        usage_action = help_menu.addAction("使用手册")
        usage_action.triggered.connect(self._on_help_usage)
        about_action = help_menu.addAction("软件信息")
        about_action.triggered.connect(self._on_help_about)
```

- [ ] **Step 2: 替换 _on_open_skills 为 _on_open_skills_dialog**

删除旧方法：
```python
    def _on_open_skills(self):
        # skills 功能尚未实现，先用 QMessageBox 占位告知用户
        QMessageBox.information(self, "skills", "Skills 功能开发中，敬请期待。")
```

新增方法：
```python
    def _on_open_skills_dialog(self):
        # 延迟 import：对话框模块只在用户点开菜单时加载，启动期不付代价
        from ui.skills_dialog import SkillsDialog
        dlg = SkillsDialog(self)
        dlg.exec()
```

- [ ] **Step 3: 验证 main_window 可 import**

```bash
python -c "from ui.main_window import MainWindow; print('MainWindow OK')"
```

Expected: `MainWindow OK`

- [ ] **Step 4: 提交**

```bash
git add ui/main_window.py
git commit -m "feat: Skills 提升为顶级菜单，接入 Skills 管理对话框"
```

---

### Task 5: 冒烟测试

- [ ] **Step 1: 启动应用手动验证**

```bash
python main.py
```

验收清单：
- [ ] 菜单栏显示「环境 | 设置 | Skills | 日志 | 帮助」
- [ ] 点击 "Skills" 菜单弹出对话框
- [ ] 左侧列出 Claude Code / CodeBuddy / Codex / Gemini / Qwen Code + 计数
- [ ] 点击左侧 Claude Code，右侧显示其 skills 列表（名称 + 描述 + checkbox）
- [ ] 取消勾选一个 skill，该 skill 目录移动到 skills-disabled/
- [ ] 重新勾选，目录移回 skills/
- [ ] 点击 "打开 Skills 目录" 在资源管理器打开对应目录
- [ ] 点击 "查看 SKILL.md" 弹出预览弹窗显示全文
- [ ] 关闭对话框，重新打开 → 状态与文件系统一致

- [ ] **Step 2: 运行全部测试确保无回归**

```bash
pytest -q
```

Expected: all tests pass

---

### Task 6: 最终提交

- [ ] **Step 1: 提交冒烟测试修正（如有）**

```bash
git add -A
git commit -m "fix: Skills 对话框冒烟测试修正"
```
