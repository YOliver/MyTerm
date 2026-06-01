import os
from collections import namedtuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QMessageBox, QFileDialog, QLabel, QSizePolicy,
)

from store.path_history import PathHistory
from store.config import AppConfig, compute_grid_shape
from store.theme import get_theme, save_theme_config, ThemeType
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import TerminalWidget
from ui.smooth_combo import SmoothComboBox

Slot = namedtuple("Slot", ["backend", "terminal", "tile"])


def _tile_border(theme) -> str:
    return f"1px solid {theme.ui.border_light}"


def _combo_style(theme, pad: str, radius: str, item_pad: str, item_height: str) -> str:
    u = theme.ui
    return (
        f"QComboBox {{"
        f"  font-family: Consolas; font-size: 13px;"
        f"  padding: {pad};"
        f"  border: 1px solid {u.border}; border-radius: {radius};"
        f"  background: {u.bg_primary}; color: {u.fg_primary};"
        f"}}"
        f"QComboBox:hover {{ border-color: {u.button_default_hover}; }}"
        f"QComboBox:focus {{ border-color: {u.button_primary}; }}"
        f"QComboBox QAbstractItemView {{"
        f"  background: {u.bg_secondary}; color: {u.fg_primary};"
        f"  selection-background-color: {u.selection_bg}; selection-color: {u.selection_fg};"
        f"  border: 1px solid {u.border}; border-radius: 4px;"
        f"  outline: none;"
        f"}}"
        f"QComboBox QAbstractItemView::item {{"
        f"  padding: {item_pad}; border-radius: 3px; min-height: {item_height};"
        f"}}"
        f"QComboBox QAbstractItemView::item:hover {{ background: {u.list_hover}; }}"
        f"QComboBox QAbstractItemView::item:selected {{ background: {u.selection_bg}; }}"
        f"QScrollBar:vertical {{ width: 6px; background: {u.scrollbar_bg}; border-radius: 3px; }}"
        f"QScrollBar::handle:vertical {{"
        f"  background: {u.scrollbar_handle}; border-radius: 3px; min-height: 20px; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
    )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MyTerm")
        self.resize(1100, 650)

        self._theme = get_theme()
        u = self._theme.ui

        self._history = PathHistory()
        self._config = AppConfig()
        self._slots: list[Slot | None] = [None] * self._config.max_terminals

        self._build_menubar()

        central = QWidget()
        central.setStyleSheet(f"background: {u.bg_primary};")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(f"background: {u.bg_secondary};")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(8, 8, 8, 8)
        topbar_layout.setSpacing(6)

        self._path_combo = SmoothComboBox()
        self._path_combo.setMinimumWidth(300)
        self._path_combo.setMinimumHeight(30)
        self._path_combo.setStyleSheet(
            _combo_style(self._theme, "5px 10px", "4px", "6px 10px", "26px"))
        self._path_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._load_history()
        topbar_layout.addWidget(self._path_combo, 1)

        self._shell_combo = SmoothComboBox()
        self._shell_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._shell_combo.setMinimumWidth(130)
        self._shell_combo.setMinimumHeight(30)
        self._shell_combo.setStyleSheet(
            _combo_style(self._theme, "5px 8px", "4px", "6px 8px", "24px"))
        for preset in self._config.shell_presets:
            self._shell_combo.addItem(preset.label)
        topbar_layout.addWidget(self._shell_combo)

        browse_btn = QPushButton("浏览")
        browse_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        browse_btn.setFixedHeight(30)
        browse_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 16px; "
            f"background: {u.button_default}; color: {u.fg_primary}; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {u.button_default_hover}; }}"
        )
        browse_btn.clicked.connect(self._on_browse)
        topbar_layout.addWidget(browse_btn)

        self._launch_btn = QPushButton("启动")
        self._launch_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._launch_btn.setFixedHeight(30)
        self._launch_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 20px; "
            f"background: {u.button_primary}; color: white; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {u.button_primary_hover}; }}"
            f"QPushButton:pressed {{ background: {u.button_primary_pressed}; }}"
        )
        self._launch_btn.clicked.connect(self._on_launch)
        topbar_layout.addWidget(self._launch_btn)

        layout.addWidget(topbar)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(1, 1, 1, 1)
        self._grid.setSpacing(1)
        # 行/列 stretch 由 _relayout 按当前槽位数动态设置
        layout.addWidget(self._grid_widget, 1)

        self.setStyleSheet(f"QMainWindow {{ background: {u.bg_primary}; }}")

    def _on_launch(self):
        path = self._path_combo.currentText().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择一个路径")
            return
        if not os.path.isdir(path):
            QMessageBox.warning(self, "错误", f"路径不存在:\n{path}")
            return

        self._history.add(path)
        self._load_history()
        cmdline = list(self._config.shell_presets[self._shell_combo.currentIndex()].command)
        self._add_terminal(path, cmdline)

    def _add_terminal(self, path, cmdline=None):
        idx = self._find_empty_slot()
        if idx is None:
            QMessageBox.warning(self, "提示", f"已达到最大数量 {self._config.max_terminals}")
            return

        backend = TerminalBackend()
        terminal = TerminalWidget(backend)
        backend.start_shell(cwd=path, columns=terminal.columns,
                            rows=terminal.rows, cmdline=cmdline)

        shell_label = self._config.shell_presets[self._shell_combo.currentIndex()].label
        tile = self._make_tile(path, terminal, idx, shell_label)
        self._slots[idx] = Slot(backend, terminal, tile)

        self._relayout()
        terminal.setFocus()

    def _make_tile(self, path, terminal, slot_idx, shell_label=""):
        u = self._theme.ui
        tile = QWidget()
        tile.setStyleSheet(f"background: {u.bg_primary}; border: {_tile_border(self._theme)};")
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(24)
        bar.setStyleSheet(f"background: {u.bg_tertiary}; border: none;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 4, 0)
        bl.setSpacing(0)

        title = f"{os.path.basename(path)}  {shell_label}"
        title_btn = QPushButton(title)
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        title_btn.setStyleSheet(
            f"QPushButton {{ font-family: Consolas; font-size: 11px; color: {u.fg_secondary};"
            " background: transparent; border: none; }"
            f"QPushButton:hover {{ color: {u.fg_primary}; text-decoration: underline; }}"
        )
        title_btn.clicked.connect(lambda _, p=path: os.startfile(p))
        bl.addWidget(title_btn)
        bl.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            f"QPushButton {{ font-size: 13px; color: {u.fg_muted}; background: transparent; border: none; border-radius: 2px; }}"
            f"QPushButton:hover {{ background: {u.button_danger_hover}; color: #fff; }}"
        )
        close_btn.clicked.connect(lambda: self._remove_terminal(slot_idx))
        bl.addWidget(close_btn)

        tl.addWidget(bar)
        tl.addWidget(terminal, 1)
        return tile

    def _remove_terminal(self, slot_idx):
        slot = self._slots[slot_idx]
        if slot is None:
            return
        slot.backend.stop()
        self._grid.removeWidget(slot.tile)
        slot.tile.deleteLater()
        self._slots[slot_idx] = None
        self._relayout()

    def _find_empty_slot(self):
        for i, s in enumerate(self._slots):
            if s is None:
                return i
        return None

    def _active_count(self):
        return sum(1 for s in self._slots if s is not None)

    def _relayout(self) -> None:
        # 1) 移除旧 widgets
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                self._grid.removeWidget(item.widget())

        # 2) 收集非空 tile
        tiles = [s for s in self._slots if s is not None]
        count = len(tiles)
        if count == 0:
            return

        # 3) 按通用算法计算最接近正方形的网格
        rows, cols = compute_grid_shape(count)

        # 4) 清掉所有旧 stretch（防止上次更大网格残留 stretch=1 的空行/空列）
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        # 5) 按新维度设置 stretch
        for r in range(rows):
            self._grid.setRowStretch(r, 1)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

        # 6) 逐个 addWidget，全部 1×1
        for i, slot in enumerate(tiles):
            self._grid.addWidget(slot.tile, i // cols, i % cols)

    def _load_history(self):
        paths = self._history.all()
        self._path_combo.clear()
        self._path_combo.addItems(paths)
        if paths:
            self._path_combo.setCurrentText(paths[0])

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择工作目录", "C:\\")
        if path:
            self._path_combo.setCurrentText(path)
            self._history.add(path)
            self._load_history()

    def _build_menubar(self):
        """主窗口顶部标准 QMenuBar，主题与 topbar 对齐。"""
        u = self._theme.ui
        menubar = self.menuBar()
        menubar.setStyleSheet(
            f"QMenuBar {{ background: {u.bg_tertiary}; color: {u.fg_primary}; }}"
            "QMenuBar::item { padding: 4px 12px; background: transparent; }"
            f"QMenuBar::item:selected {{ background: {u.selection_bg}; }}"
            f"QMenu {{ background: {u.bg_secondary}; color: {u.fg_primary}; border: 1px solid {u.border}; }}"
            "QMenu::item { padding: 6px 24px; }"
            f"QMenu::item:selected {{ background: {u.selection_bg}; }}"
        )
        env_menu = menubar.addMenu("环境")
        check_action = env_menu.addAction("检测依赖")
        check_action.triggered.connect(self._on_check_env)

        settings_menu = menubar.addMenu("设置")
        shell_action = settings_menu.addAction("AI CLI 配置...")
        shell_action.triggered.connect(self._on_open_settings)
        cli_install_action = settings_menu.addAction("CLI 安装")
        cli_install_action.triggered.connect(self._on_open_cli_install)
        skills_action = settings_menu.addAction("skills")
        skills_action.triggered.connect(self._on_open_skills)

        # 主题切换子菜单
        theme_menu = settings_menu.addMenu("主题")
        dark_action = theme_menu.addAction("深色")
        dark_action.triggered.connect(lambda: self._switch_theme(ThemeType.DARK))
        light_action = theme_menu.addAction("浅色")
        light_action.triggered.connect(lambda: self._switch_theme(ThemeType.LIGHT))

        log_menu = menubar.addMenu("日志")
        open_log_action = log_menu.addAction("打开日志目录")
        open_log_action.triggered.connect(self._on_open_log_dir)

        help_menu = menubar.addMenu("帮助")
        usage_action = help_menu.addAction("使用说明")
        usage_action.triggered.connect(self._on_help_usage)
        about_action = help_menu.addAction("软件信息")
        about_action.triggered.connect(self._on_help_about)

        contact_menu = menubar.addMenu("联系我")
        contact_action = contact_menu.addAction("打开百度")
        contact_action.triggered.connect(self._on_contact)

    def _switch_theme(self, theme_type: ThemeType) -> None:
        """保存主题配置，提示用户重启后生效。"""
        save_theme_config(theme_type)
        theme_name = "浅色" if theme_type == ThemeType.LIGHT else "深色"
        QMessageBox.information(
            self, "主题切换",
            f"主题已切换为「{theme_name}」。\n重启应用后生效。"
        )

    def _on_contact(self):
        """打开浏览器跳转到百度。"""
        import webbrowser
        webbrowser.open("https://www.baidu.com")

    def _on_check_env(self):
        # 延迟 import：对话框模块只在用户点开菜单时加载，启动期不付代价
        from ui.env_check_dialog import EnvCheckDialog
        dlg = EnvCheckDialog(self)
        dlg.exec()

    def _on_open_settings(self):
        # 延迟 import 同上
        from ui.shell_presets_dialog import ShellPresetsDialog
        dlg = ShellPresetsDialog(self._config.shell_presets, self)
        dlg.presets_changed.connect(self._on_presets_changed)
        dlg.exec()

    def _on_open_cli_install(self):
        # 延迟 import：对话框模块只在用户点开菜单时加载，启动期不付代价
        from ui.cli_install_dialog import CliInstallDialog
        dlg = CliInstallDialog(self)
        # 安装/卸载成功后联动刷新启动下拉框；信号无参，复用 _on_presets_changed
        # 时套层 lambda，把可选参数留给原签名（ShellPresetsDialog 那边带 list）
        dlg.presets_changed.connect(lambda: self._on_presets_changed(None))
        dlg.exec()

    def _on_open_skills(self):
        # skills 功能尚未实现，先用 QMessageBox 占位告知用户
        QMessageBox.information(self, "skills", "Skills 功能开发中，敬请期待。")

    def _on_open_log_dir(self):
        from store.paths import log_dir
        os.startfile(str(log_dir()))

    def _on_presets_changed(self, _new_presets=None):
        """设置面板保存后：重读盘 + 重填启动下拉框，按 label 回填 currentIndex。

        参数 ``_new_presets`` 在 ShellPresetsDialog 的信号里是新列表；CliInstallDialog
        触发时为 None。两种调用都直接走 reload，所以参数其实可忽略——保留只是为了
        signature 兼容旧信号绑定。

        已开终端不动：backend 已经在跑，没必要重启。
        """
        self._config.reload_shell_presets()
        old_label = self._shell_combo.currentText()
        self._shell_combo.blockSignals(True)
        self._shell_combo.clear()
        for preset in self._config.shell_presets:
            self._shell_combo.addItem(preset.label)
        idx = self._shell_combo.findText(old_label)
        self._shell_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._shell_combo.blockSignals(False)

    def _on_help_usage(self):
        self._open_help("使用说明", "docs/help/usage.md")

    def _on_help_about(self):
        self._open_help("软件信息", "docs/help/about.md")

    def _open_help(self, title: str, rel_path: str) -> None:
        """统一帮助对话框入口：延迟 import + 内嵌资源路径解析。"""
        from ui.help_dialog import HelpDialog
        from store.paths import resource_path
        HelpDialog(title, resource_path(rel_path), self).exec()
