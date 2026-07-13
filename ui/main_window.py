import logging
import os
import time
from collections import namedtuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QMessageBox, QFileDialog, QLabel, QSizePolicy, QScrollBar,
)

from store.path_history import PathHistory
from store.config import AppConfig, compute_grid_shape_for, LayoutMode
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import (
    TerminalWidget,
    scroll_offset_to_slider_value,
    slider_value_to_scroll_offset,
)
from ui.smooth_combo import SmoothComboBox

Slot = namedtuple("Slot", ["backend", "terminal", "tile"])

logger = logging.getLogger(__name__)

TILE_BORDER = "1px solid #444"

# 终端右侧滚动条样式：暗色窄滚动条，与 COMBO_STYLE 里的下拉滚动条视觉一致。
# 注意：单独的 QScrollBar 部件（不是嵌在 view 里）样式表必须用顶级选择器，
# 不能用 QComboBox QScrollBar 那种后代选择器。
TERMINAL_SCROLLBAR_STYLE = (
    "QScrollBar:vertical {"
    "  width: 10px; background: #1e1e1e; border: none; margin: 0;"
    "}"
    "QScrollBar::handle:vertical {"
    "  background: #555; border-radius: 5px; min-height: 24px;"
    "}"
    "QScrollBar::handle:vertical:hover { background: #777; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
    "  height: 0; background: none;"
    "}"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
    "  background: none;"
    "}"
)

COMBO_STYLE = (
    "QComboBox {{"
    "  font-family: Consolas; font-size: 13px;"
    "  padding: {};"
    "  border: 1px solid #555; border-radius: {};"
    "  background: #1e1e1e; color: #ccc;"
    "}}"
    "QComboBox:hover {{ border-color: #777; }}"
    "QComboBox:focus {{ border-color: #0e639c; }}"
    "QComboBox QAbstractItemView {{"
    "  background: #252526; color: #ccc;"
    "  selection-background-color: #094771; selection-color: #fff;"
    "  border: 1px solid #555; border-radius: 4px;"
    "  outline: none;"
    "}}"
    "QComboBox QAbstractItemView::item {{"
    "  padding: {}; border-radius: 3px; min-height: {};"
    "}}"
    "QComboBox QAbstractItemView::item:hover {{ background: #2a2d2e; }}"
    "QComboBox QAbstractItemView::item:selected {{ background: #094771; }}"
    "QScrollBar:vertical {{ width: 6px; background: #1e1e1e; border-radius: 3px; }}"
    "QScrollBar::handle:vertical {{"
    "  background: #555; border-radius: 3px; min-height: 20px; }}"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
    "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}"
)


class MainWindow(QMainWindow):
    def __init__(self, store=None) -> None:
        super().__init__()
        self.setWindowTitle("MyTerm")
        self.resize(1100, 650)
        logger.info("主窗口初始化")

        self._store = store  # 可能为 None（旧调用方兼容）
        self._history = PathHistory(store) if store is not None else PathHistory()
        self._config = AppConfig(store) if store is not None else AppConfig()
        self._slots: list[Slot | None] = [None] * self._config.max_terminals

        self._build_menubar()

        central = QWidget()
        central.setStyleSheet("background: #1e1e1e;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet("background: #252526;")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(8, 8, 8, 8)
        topbar_layout.setSpacing(6)

        self._path_combo = SmoothComboBox()
        self._path_combo.setMinimumWidth(300)
        self._path_combo.setMinimumHeight(30)
        self._path_combo.setStyleSheet(
            COMBO_STYLE.format("5px 10px", "4px", "6px 10px", "26px"))
        self._path_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._load_history()
        topbar_layout.addWidget(self._path_combo, 1)

        self._shell_combo = SmoothComboBox()
        self._shell_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._shell_combo.setMinimumWidth(130)
        self._shell_combo.setMinimumHeight(30)
        self._shell_combo.setStyleSheet(
            COMBO_STYLE.format("5px 8px", "4px", "6px 8px", "24px"))
        self._rebuild_shell_combo()
        topbar_layout.addWidget(self._shell_combo)

        browse_btn = QPushButton("浏览")
        browse_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        browse_btn.setFixedHeight(30)
        browse_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 16px; "
            "background: #444; color: #ccc; border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #555; }"
        )
        browse_btn.clicked.connect(self._on_browse)
        topbar_layout.addWidget(browse_btn)

        self._launch_btn = QPushButton("启动")
        self._launch_btn.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._launch_btn.setFixedHeight(30)
        self._launch_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 20px; "
            "background: #0e639c; color: white; border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #1177bb; }"
            "QPushButton:pressed { background: #094771; }"
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

        self.setStyleSheet("QMainWindow { background: #1e1e1e; }")

    def _on_launch(self):
        t0 = time.perf_counter()
        path = self._path_combo.currentText().strip()
        if not path:
            logger.info("_on_launch [%.1fms] 未选择路径，取消", 0.0)
            QMessageBox.warning(self, "提示", "请先选择一个路径")
            return
        if not os.path.isdir(path):
            t1 = (time.perf_counter() - t0) * 1000
            logger.warning("_on_launch [%.1fms] 启动路径不存在: %s", t1, path)
            QMessageBox.warning(self, "错误", f"路径不存在:\n{path}")
            return

        combo_idx = self._shell_combo.currentIndex()
        presets = self._config.shell_presets
        if combo_idx < 0 or combo_idx >= len(presets):
            t1 = (time.perf_counter() - t0) * 1000
            logger.error("_on_launch [%.1fms] shell_combo 索引越界: idx=%d, presets=%d",
                         t1, combo_idx, len(presets))
            QMessageBox.warning(self, "错误", "Shell 预设索引异常，请重新选择")
            return
        preset = presets[combo_idx]
        t1 = (time.perf_counter() - t0) * 1000
        logger.info("_on_launch [%.1fms] 预设读取完成: label=%s cmd=%s", t1, preset.label, preset.raw_command)

        self._history.add(path)
        t2 = (time.perf_counter() - t0) * 1000
        logger.info("_on_launch [%.1fms] 路径历史已写入 path=%s", t2, path)

        self._load_history()
        t3 = (time.perf_counter() - t0) * 1000
        logger.info("_on_launch [%.1fms] 下拉框已刷新", t3)

        cmdline = list(preset.command)
        t4 = (time.perf_counter() - t0) * 1000
        logger.info("_on_launch [%.1fms] 校验通过，进入 _add_terminal cmd=%s", t4, cmdline)
        self._add_terminal(path, cmdline)
        t5 = (time.perf_counter() - t0) * 1000
        logger.info("_on_launch [%.1fms] 完成", t5)

    def _add_terminal(self, path, cmdline=None):
        t0 = time.perf_counter()
        idx = self._find_empty_slot()
        if idx is None:
            logger.warning("_add_terminal [%.1fms] 终端槽位已满 (max=%d)",
                           (time.perf_counter() - t0) * 1000, self._config.max_terminals)
            QMessageBox.warning(self, "提示", f"已达到最大数量 {self._config.max_terminals}")
            return

        active = self._active_count()
        t1 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] 空槽位 idx=%d (已用=%d/%d) cmd=%s",
                    t1, idx, active, self._config.max_terminals, cmdline)

        backend = TerminalBackend()
        t2 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] TerminalBackend 构造完成", t2)

        terminal = TerminalWidget(backend)
        t3 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] TerminalWidget 构造完成", t3)

        start_shell_t0 = time.perf_counter()
        backend.start_shell(cwd=path, columns=terminal.columns,
                            rows=terminal.rows, cmdline=cmdline)
        spawn_ms = (time.perf_counter() - start_shell_t0) * 1000
        t4 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] backend.start_shell() 返回，耗时 %.1fms", t4, spawn_ms)

        backend.process_exited.connect(lambda _code, i=idx: self._remove_terminal(i))
        t5 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] process_exited 信号已连接", t5)

        shell_label = self._config.shell_presets[self._shell_combo.currentIndex()].label
        tile = self._make_tile(path, terminal, idx, shell_label)
        t6 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] _make_tile 完成", t6)

        self._slots[idx] = Slot(backend, terminal, tile)
        t7 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] Slot 已注册 slot=%d", t7, idx)

        self._relayout()
        t8 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] _relayout 完成", t8)

        terminal.setFocus()
        t9 = (time.perf_counter() - t0) * 1000
        logger.info("_add_terminal [%.1fms] setFocus 完成，终端会话创建完成 slot=%d", t9, idx)

    def _make_tile(self, path, terminal, slot_idx, shell_label=""):
        tile = QWidget()
        tile.setStyleSheet(f"background: #1e1e1e; border: {TILE_BORDER};")
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(24)
        bar.setStyleSheet("background: #2d2d2d; border: none;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 4, 0)
        bl.setSpacing(0)

        title = f"{os.path.basename(path)}  {shell_label}"
        title_btn = QPushButton(title)
        title_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        title_btn.setStyleSheet(
            "QPushButton { font-family: Consolas; font-size: 11px; color: #aaa;"
            " background: transparent; border: none; }"
            "QPushButton:hover { color: #ddd; text-decoration: underline; }"
        )
        title_btn.clicked.connect(lambda _, p=path: os.startfile(p))
        bl.addWidget(title_btn)
        bl.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { font-size: 13px; color: #999; background: transparent; border: none; border-radius: 2px; }"
            "QPushButton:hover { background: #c42b1c; color: #fff; }"
        )
        close_btn.clicked.connect(lambda: self._remove_terminal(slot_idx))
        bl.addWidget(close_btn)

        # 终端 + 右侧滚动条：水平并排。滚动条占用一点宽度，terminal 自适应剩余宽度，
        # 触发 _apply_resize 让 PTY cols 重新计算，无副作用。
        body = QWidget()
        body.setStyleSheet("background: transparent; border: none;")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(terminal, 1)

        scrollbar = QScrollBar(Qt.Orientation.Vertical, body)
        scrollbar.setStyleSheet(TERMINAL_SCROLLBAR_STYLE)
        scrollbar.setCursor(Qt.CursorShape.ArrowCursor)
        body_layout.addWidget(scrollbar)

        # 双向同步：terminal 滚动状态变 → 刷新滚动条；滚动条值变 → 设置 terminal offset。
        # _sync_scrollbar 内部用 blockSignals 防回环，避免 valueChanged 反过来再触发它。
        def _sync_scrollbar():
            offset, history_len, visible_rows = terminal.get_scroll_state()
            # 用 blockSignals 避免 setRange/setValue 触发 valueChanged 又回写 terminal,
            # 形成 emit → set → emit 死循环。
            scrollbar.blockSignals(True)
            try:
                scrollbar.setRange(0, history_len)
                # page_step 让滑块大小反映"一屏"，方便用户感知比例
                scrollbar.setPageStep(max(1, visible_rows))
                scrollbar.setSingleStep(1)
                scrollbar.setValue(scroll_offset_to_slider_value(offset, history_len))
                # history_len == 0 时滚动条没有可拖区间，禁用更直观
                scrollbar.setEnabled(history_len > 0)
            finally:
                scrollbar.blockSignals(False)

        def _on_slider_changed(value: int):
            _, history_len, _ = terminal.get_scroll_state()
            terminal.set_scroll_offset(slider_value_to_scroll_offset(value, history_len))

        terminal.scroll_state_changed.connect(_sync_scrollbar)
        scrollbar.valueChanged.connect(_on_slider_changed)
        # 初始同步一次（终端刚创建，history_len=0，禁用滚动条）
        _sync_scrollbar()

        tl.addWidget(bar)
        tl.addWidget(body, 1)
        return tile

    def _remove_terminal(self, slot_idx):
        slot = self._slots[slot_idx]
        if slot is None:
            logger.warning("_remove_terminal: slot=%d 已经为空，跳过", slot_idx)
            return
        is_alive = slot.backend.isRunning()
        logger.info("关闭终端会话: slot=%d, backend_alive=%s, 槽位=%s",
                     slot_idx, is_alive,
                     ["空" if s is None else "占" for s in self._slots])
        # 断开 process_exited 信号，防止 stop() 让后端线程退出后跨线程信号被排队投递，
        # 导致 _remove_terminal 被重复调用（第二次进来 slot 已经是 None，只打警告）。
        # 每个 backend 只有一条连接（_add_terminal 里的 lambda），断掉不影响其他终端。
        try:
            slot.backend.process_exited.disconnect()
        except Exception:
            pass
        slot.backend.stop()
        self._grid.removeWidget(slot.tile)
        slot.tile.deleteLater()
        self._slots[slot_idx] = None
        logger.debug("终端已移除 slot=%d, 槽位=%s",
                      slot_idx, ["空" if s is None else "占" for s in self._slots])
        self._relayout()

    def _find_empty_slot(self):
        snapshot = ["空" if s is None else "占" for s in self._slots]
        for i, s in enumerate(self._slots):
            if s is None:
                logger.debug("_find_empty_slot: 槽位=%s → 返回 %d", snapshot, i)
                return i
        logger.warning("_find_empty_slot: 无空槽位, 槽位=%s", snapshot)
        return None

    def _active_count(self):
        return sum(1 for s in self._slots if s is not None)

    def _relayout(self) -> None:
        # 1) 移除旧 widgets（tile 只 remove 不 delete，占位符在下文统一清理）
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                self._grid.removeWidget(item.widget())

        # 2) 收集非空 tile
        tiles = [s for s in self._slots if s is not None]
        count = len(tiles)
        if count == 0:
            return

        # 3) 根据布局模式计算行列
        rows, cols = compute_grid_shape_for(count, self._config.layout_mode)
        total_cells = rows * cols

        if logger.isEnabledFor(logging.INFO):
            active = self._active_count()
            logger.info("_relayout: count=%d mode=%s grid=%dx%d total=%d (active=%d)",
                        count, self._config.layout_mode, rows, cols, total_cells, active)

        # 4) 清掉所有旧 stretch
        for r in range(self._grid.rowCount()):
            self._grid.setRowStretch(r, 0)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)

        # 5) 按新维度设置 stretch
        for r in range(rows):
            self._grid.setRowStretch(r, 1)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

        # 6) 放置 tile
        for i, slot in enumerate(tiles):
            self._grid.addWidget(slot.tile, i // cols, i % cols)

        # 7) 固定模式下填占位符（先清旧再建新）
        if hasattr(self, '_placeholders'):
            for p in self._placeholders:
                p.deleteLater()
        self._placeholders = []

        if self._config.layout_mode != LayoutMode.AUTO:
            for i in range(count, total_cells):
                placeholder = QWidget()
                placeholder.setStyleSheet(
                    "background: #1a1a1a; border: 1px solid #333; border-radius: 2px;"
                )
                self._grid.addWidget(placeholder, i // cols, i % cols)
                self._placeholders.append(placeholder)

    def _on_layout_switch(self, mode) -> None:
        """视图菜单切换布局模式。"""
        self._config.layout_mode = mode
        self._config.save()
        self._update_layout_menu_check()
        self._relayout()

    def _update_layout_menu_check(self) -> None:
        """同步菜单选中状态。"""
        for mode, action in self._layout_actions.items():
            action.setChecked(mode == self._config.layout_mode)

    def _load_history(self):
        paths = self._history.all()
        logger.debug("_load_history: 加载 %d 条路径记录", len(paths))
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
        # ── 视图 ──
        view_menu = menubar.addMenu("视图")
        self._layout_actions: dict[LayoutMode, QAction] = {}
        for mode, label in [
            (LayoutMode.AUTO, "自动布局"),
            (LayoutMode.QUAD, "四象限 2×2"),
            (LayoutMode.HORIZONTAL, "横排 1×N"),
            (LayoutMode.VERTICAL, "竖排 N×1"),
        ]:
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked, m=mode: self._on_layout_switch(m)
            )
            self._layout_actions[mode] = action
        self._update_layout_menu_check()

        # ── 环境 ──
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
        dlg = CliInstallDialog(self, store=self._store)
        # 安装/卸载成功后联动刷新启动下拉框；信号无参，复用 _on_presets_changed
        # 时套层 lambda，把可选参数留给原签名（ShellPresetsDialog 那边带 list）
        dlg.presets_changed.connect(lambda: self._on_presets_changed(None))
        dlg.exec()

    def _on_open_skills_dialog(self):
        # 延迟 import：对话框模块只在用户点开菜单时加载，启动期不付代价
        from ui.skills_dialog import SkillsDialog
        dlg = SkillsDialog(self)
        dlg.exec()

    def _on_open_log_dir(self):
        from store.paths import log_dir
        os.startfile(str(log_dir()))

    def _on_presets_changed(self, new_presets=None):
        """设置面板或 CLI 安装/卸载后：保存 → 重读 → 重建下拉框。"""
        if new_presets is not None and self._store is not None:
            from store import shell_presets
            shell_presets.save(new_presets, store=self._store)
        self._config.reload_shell_presets()
        logger.info("Shell 预设已刷新, 共 %d 条", len(self._config.shell_presets))
        self._rebuild_shell_combo()

    def on_data_loaded(self):
        """DataWorker 数据加载完毕后刷新 UI。"""
        self._load_history()
        self._config.reload_shell_presets()
        self._rebuild_shell_combo()

    def _rebuild_shell_combo(self):
        """重建 shell 下拉框。清空后重新填入预设；保留当前选中项。"""
        old_label = self._shell_combo.currentText()
        self._shell_combo.blockSignals(True)
        self._shell_combo.clear()
        for preset in self._config.shell_presets:
            self._shell_combo.addItem(preset.label)
        if old_label:
            idx = self._shell_combo.findText(old_label)
            if idx >= 0:
                self._shell_combo.setCurrentIndex(idx)
        self._shell_combo.blockSignals(False)

    def _on_help_welcome(self):
        self._open_help("欢迎", "helpdocs/welcome.md")

    def _on_help_usage(self):
        self._open_help("使用手册", "helpdocs/使用手册.md")

    def _on_help_about(self):
        self._open_help("软件信息", "helpdocs/about.md")

    def _open_help(self, title: str, rel_path: str) -> None:
        """统一帮助对话框入口：延迟 import + 内嵌资源路径解析。"""
        from ui.help_dialog import HelpDialog
        from store.paths import resource_path
        HelpDialog(title, resource_path(rel_path), self).exec()
