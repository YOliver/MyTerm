"""Skills 管理对话框：按 CLI 分组浏览、启用/禁用、预览 SKILL.md。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
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
    "QTextEdit {"
    "  background: #1e1e1e; color: #ccc;"
    "  font-family: Consolas; font-size: 13px;"
    "  border: 1px solid #3a3a3a; border-radius: 4px;"
    "}"
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
        viewer.setAutoFillBackground(True)
        # 强制深色背景：覆盖 Fusion 样式的浅色默认值
        p = viewer.palette()
        p.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
        p.setColor(QPalette.ColorRole.Text, QColor(204, 204, 204))
        viewer.setPalette(p)
        layout.addWidget(viewer, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


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
        # 记录用户最后一次点击的 skill 名（用于预览按钮，只存名称避免 stale reference）
        self._selected_skill_name: str | None = None

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
        self._skill_container.setStyleSheet("QWidget { background: #1e1e1e; }")
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
            row_widget.setStyleSheet("QWidget { background: #1e1e1e; }")
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
            desc_label.setWordWrap(True)
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
