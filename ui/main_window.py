import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from store.path_history import PathHistory
from backend.terminal_backend import TerminalBackend
from ui.terminal_widget import TerminalWidget


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

        self._path_combo = QComboBox()
        self._path_combo.setMinimumWidth(300)
        self._path_combo.setStyleSheet(
            "QComboBox { font-family: Consolas; font-size: 13px; padding: 4px 8px; "
            "border: 1px solid #555; border-radius: 3px; background: #1e1e1e; color: #ccc; }"
            "QComboBox QAbstractItemView { background: #1e1e1e; color: #ccc; "
            "selection-background-color: #094771; }"
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
