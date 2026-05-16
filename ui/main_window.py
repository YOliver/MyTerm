import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QComboBox, QPushButton, QMessageBox, QFileDialog, QLabel,
    QAbstractItemView, QSizePolicy,
)
from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QIcon
from store.path_history import PathHistory
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import TerminalWidget


class SmoothComboBox(QComboBox):
    """下拉抽屉动画 — setMask 裁剪，不碰几何属性避免定位漂移"""

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QAbstractItemView)
        if not popup or not popup.isVisible():
            return

        # 始终从顶部展开：先滚到顶部，再修正容器位置到路径框正下方
        popup.scrollToTop()
        container = popup.parent()
        if container:
            from PySide6.QtWidgets import QFrame
            container.setFrameShape(QFrame.Shape.NoFrame)
            container.setStyleSheet("background: #252526;")
            # 强制容器顶部对齐路径框底部
            combo_bottom = self.mapToGlobal(self.rect().bottomLeft())
            geo = container.geometry()
            geo.moveTop(combo_bottom.y())
            container.setGeometry(geo)
        popup.setViewportMargins(0, 0, 0, 0)

        from PySide6.QtGui import QRegion

        w = popup.width()
        h = popup.height()

        anim = QVariantAnimation()
        anim.setDuration(180)
        anim.setStartValue(2)
        anim.setEndValue(h)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.valueChanged.connect(lambda v: popup.setMask(QRegion(0, 0, w, v)))
        anim.finished.connect(popup.clearMask)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim


MAX_TERMINALS = 4
TILE_BORDER = "1px solid #444"

SHELL_PRESETS = [
    ("<powershell>", ["powershell.exe"]),
    ("<claude -r>", ["powershell.exe", "-NoExit", "-Command", "claude -r"]),
    ("<cmd>",        ["cmd.exe"]),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyTerm")
        self.resize(1100, 650)

        icon = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.png")
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))

        self._history = PathHistory()
        self._slots = [None] * MAX_TERMINALS  # each: dict or None

        central = QWidget()
        central.setStyleSheet("background: #1e1e1e;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- topbar ---
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
            "QComboBox {"
            "  font-family: Consolas; font-size: 13px;"
            "  padding: 5px 10px;"
            "  border: 1px solid #555; border-radius: 4px;"
            "  background: #1e1e1e; color: #ccc;"
            "}"
            "QComboBox:hover { border-color: #777; }"
            "QComboBox:focus { border-color: #0e639c; }"
            "QComboBox QAbstractItemView {"
            "  background: #252526; color: #ccc;"
            "  selection-background-color: #094771; selection-color: #fff;"
            "  border: 1px solid #555; border-radius: 4px;"
            "  outline: none;"
            "}"
            "QComboBox QAbstractItemView::item {"
            "  padding: 6px 10px; border-radius: 3px; min-height: 26px;"
            "}"
            "QComboBox QAbstractItemView::item:hover {"
            "  background: #2a2d2e;"
            "}"
            "QComboBox QAbstractItemView::item:selected {"
            "  background: #094771;"
            "}"
            "QScrollBar:vertical {"
            "  width: 6px; background: #1e1e1e; border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #555; border-radius: 3px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: none;"
            "}"
        )
        self._load_history()
        topbar_layout.addWidget(self._path_combo, 1)

        self._shell_combo = SmoothComboBox()
        self._shell_combo.setMinimumWidth(130)
        self._shell_combo.setMinimumHeight(30)
        self._shell_combo.setStyleSheet(
            "QComboBox {"
            "  font-family: Consolas; font-size: 13px;"
            "  padding: 5px 8px;"
            "  border: 1px solid #555; border-radius: 4px;"
            "  background: #1e1e1e; color: #ccc;"
            "}"
            "QComboBox:hover { border-color: #777; }"
            "QComboBox:focus { border-color: #0e639c; }"
            "QComboBox QAbstractItemView {"
            "  background: #252526; color: #ccc;"
            "  selection-background-color: #094771; selection-color: #fff;"
            "  border: 1px solid #555; outline: none;"
            "}"
            "QComboBox QAbstractItemView::item {"
            "  padding: 6px 8px; min-height: 24px;"
            "}"
            "QComboBox QAbstractItemView::item:hover {"
            "  background: #2a2d2e;"
            "}"
            "QComboBox QAbstractItemView::item:selected {"
            "  background: #094771;"
            "}"
            "QScrollBar:vertical {"
            "  width: 6px; background: #1e1e1e; border-radius: 3px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: #555; border-radius: 3px; min-height: 20px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: none;"
            "}"
        )
        for label, _ in SHELL_PRESETS:
            self._shell_combo.addItem(label)
        topbar_layout.addWidget(self._shell_combo)

        browse_btn = QPushButton("浏览")
        browse_btn.setFixedHeight(30)
        browse_btn.setStyleSheet(
            "QPushButton { font-size: 13px; padding: 0 16px; "
            "background: #444; color: #ccc; border: none; border-radius: 3px; }"
            "QPushButton:hover { background: #555; }"
        )
        browse_btn.clicked.connect(self._on_browse)
        topbar_layout.addWidget(browse_btn)

        self._launch_btn = QPushButton("启动")
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

        # --- grid area ---
        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setContentsMargins(1, 1, 1, 1)
        self._grid.setSpacing(1)
        for r in range(2):
            self._grid.setRowStretch(r, 1)
        for c in range(2):
            self._grid.setColumnStretch(c, 1)
        layout.addWidget(self._grid_widget, 1)

        self.setStyleSheet("QMainWindow { background: #1e1e1e; }")

    # -----------------------------------------------------------------

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
        cmdline = SHELL_PRESETS[self._shell_combo.currentIndex()][1]
        self._add_terminal(path, cmdline)

    def _add_terminal(self, path, cmdline=None):
        idx = self._find_empty_slot()
        if idx is None:
            QMessageBox.warning(self, "提示", f"已达到最大数量 {MAX_TERMINALS}")
            return

        backend = TerminalBackend()
        terminal = TerminalWidget(backend)
        cols = terminal._screen.columns
        rows = terminal._screen.lines
        backend.start_shell(cwd=path, columns=cols, rows=rows, cmdline=cmdline)

        shell_label = SHELL_PRESETS[self._shell_combo.currentIndex()][0]
        tile = self._make_tile(path, terminal, idx, shell_label)
        self._slots[idx] = {"backend": backend, "terminal": terminal, "tile": tile}

        self._relayout()
        terminal.setFocus()

    def _make_tile(self, path, terminal, slot_idx, shell_label=""):
        tile = QWidget()
        tile.setStyleSheet(f"background: #1e1e1e; border: {TILE_BORDER};")
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        # title bar
        bar = QWidget()
        bar.setFixedHeight(24)
        bar.setStyleSheet("background: #2d2d2d; border: none;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 4, 0)
        bl.setSpacing(0)

        title = f"{os.path.basename(path)}  {shell_label}"
        label = QLabel(title)
        label.setStyleSheet("font-family: Consolas; font-size: 11px; color: #aaa; background: transparent; border: none;")
        bl.addWidget(label)
        bl.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { font-size: 13px; color: #999; background: transparent; border: none; border-radius: 2px; }"
            "QPushButton:hover { background: #c42b1c; color: #fff; }"
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
        slot["backend"].stop()
        # Remove from grid and delete
        self._grid.removeWidget(slot["tile"])
        slot["tile"].deleteLater()
        self._slots[slot_idx] = None
        self._relayout()

    def _find_empty_slot(self):
        for i, s in enumerate(self._slots):
            if s is None:
                return i
        return None

    def _active_count(self):
        return sum(1 for s in self._slots if s is not None)

    def _relayout(self):
        # Clear grid
        for i in reversed(range(self._grid.count())):
            item = self._grid.itemAt(i)
            if item and item.widget():
                self._grid.removeWidget(item.widget())

        # Collect non-None slots in order
        tiles = [s for s in self._slots if s is not None]
        count = len(tiles)

        if count == 0:
            return

        spans = {
            1: [(0, 0, 2, 2)],
            2: [(0, 0, 2, 1), (0, 1, 2, 1)],
            3: [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)],
            4: [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)],
        }

        for i, (r, c, rs, cs) in enumerate(spans[count]):
            self._grid.addWidget(tiles[i]["tile"], r, c, rs, cs)

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
