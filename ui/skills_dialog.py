"""Skills 浏览对话框：按 CLI 分组展示全局 skills，支持预览 SKILL.md。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from store.skills_manager import (
    CLI_DISPLAY_NAMES,
    CLI_SKILLS_DIRS,
    SkillInfo,
    git_pull_skill,
    load_skill_content,
    open_skills_dir,
    scan_skills,
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
    """Skills 浏览对话框：左侧 CLI 列表，右侧 skill 清单 + 预览按钮。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skills 浏览")
        self.resize(800, 520)
        self.setStyleSheet(_DIALOG_STYLE)

        self._cli_ids = list(CLI_SKILLS_DIRS.keys())
        self._current_cli: str | None = None
        self._skills_cache: dict[str, list[SkillInfo]] = {}
        # 记录用户最后一次点击的 skill 名 + 按钮（用于高亮 + 预览）
        self._selected_skill_name: str | None = None
        self._selected_btn: QPushButton | None = None

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
        """扫描所有 CLI 并填充左侧列表（仅统计启用的 skills）。"""
        self._cli_list.clear()
        for cli_id in self._cli_ids:
            skills = [s for s in scan_skills(cli_id) if s.enabled]
            self._skills_cache[cli_id] = skills
            display = CLI_DISPLAY_NAMES.get(cli_id, cli_id)
            count = len(skills)
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
        self._selected_skill_name = None
        self._selected_btn = None
        skills = self._skills_cache.get(cli_id, [])
        self._rebuild_skill_list(skills)

    def _rebuild_skill_list(self, skills: list[SkillInfo]) -> None:
        """重新构建右侧 skill 列表。"""
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

        # skill 名称按钮的两种样式
        _SKILL_BTN_BASE = (
            "QPushButton { color: #ccc; font-family: Consolas; font-size: 12px;"
            " background: transparent; border: none; text-align: left; padding: 4px 8px;"
            " border-radius: 3px; }"
            "QPushButton:hover { color: #fff; background: #2a2d2e; }"
        )
        _SKILL_BTN_SELECTED = (
            "QPushButton { color: #fff; font-family: Consolas; font-size: 12px;"
            " background: #094771; border: none; text-align: left; padding: 4px 8px;"
            " border-radius: 3px; }"
            "QPushButton:hover { background: #0e639c; }"
        )

        for skill in skills:
            row_widget = QWidget()
            row_widget.setStyleSheet("QWidget { background: #1e1e1e; }")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(4, 3, 4, 3)
            row_layout.setSpacing(4)

            # 更新图标按钮
            icon_btn = QPushButton("↻", row_widget)
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

        self._skill_layout.addStretch()

    def _select_skill(self, btn: QPushButton, skill_name: str) -> None:
        """点击 skill 名称：取消旧高亮，高亮新按钮，记录选中 skill。"""
        # 取消旧按钮高亮
        if self._selected_btn is not None:
            self._selected_btn.setStyleSheet(
                "QPushButton { color: #ccc; font-family: Consolas; font-size: 12px;"
                " background: transparent; border: none; text-align: left; padding: 4px 8px;"
                " border-radius: 3px; }"
                "QPushButton:hover { color: #fff; background: #2a2d2e; }"
            )
        # 高亮新按钮
        btn.setStyleSheet(
            "QPushButton { color: #fff; font-family: Consolas; font-size: 12px;"
            " background: #094771; border: none; text-align: left; padding: 4px 8px;"
            " border-radius: 3px; }"
            "QPushButton:hover { background: #0e639c; }"
        )
        self._selected_btn = btn
        self._selected_skill_name = skill_name

    def _on_open_dir(self) -> None:
        """打开当前选中 CLI 的 skills 目录。"""
        if self._current_cli is None:
            return
        open_skills_dir(self._current_cli)

    def _on_preview(self) -> None:
        """预览当前选中 skill 的 SKILL.md 全文。

        优先取用户最后一次点击的 skill 名（``_selected_skill_name``），
        fallback 到列表第一个。
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
