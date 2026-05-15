import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QMessageBox, QFileDialog,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QAbstractAnimation
from store.path_history import PathHistory
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import TerminalWidget


class SmoothComboBox(QComboBox):
    """下拉抽屉动画 — 用 setMask 裁剪，不碰几何属性避免定位漂移"""

    def showPopup(self):
        super().showPopup()
        popup = self.findChild(QAbstractItemView)
        if not popup or not popup.isVisible():
            return

        from PySide6.QtGui import QRegion
        from PySide6.QtCore import QRect

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyTerm")
        self.resize(900, 550)

        self._history = PathHistory()
        self._backend = TerminalBackend()

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
            "  padding: 4px; outline: none;"
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

        self._terminal = TerminalWidget(self._backend)
        layout.addWidget(self._terminal, 1)

        self.setStyleSheet("QMainWindow { background: #1e1e1e; }")

    def _load_history(self):
        paths = self._history.all()
        self._path_combo.clear()
        self._path_combo.addItems(paths)
        if paths:
            self._path_combo.setCurrentText(paths[0])

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
        cols = self._terminal._screen.columns
        rows = self._terminal._screen.lines
        self._backend.start_shell(cwd=path, columns=cols, rows=rows)
        self._terminal.setFocus()

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择工作目录", "C:\\")
        if path:
            self._path_combo.setCurrentText(path)
            self._history.add(path)
            self._load_history()
