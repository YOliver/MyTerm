"""环境检测对话框：表格逐项异步显示检测进度。

后台线程跑 check_all()，每出一项 emit 信号，UI 主线程把对应行刷新成
✓/✗。关闭对话框时若 worker 还在跑会请求中断并等待，避免 thread
destroyed 警告。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from store.env_check import ENV_SPECS, EnvResult, check_all


_DIALOG_STYLE = (
    "QDialog { background: #1e1e1e; }"
    "QTableWidget {"
    "  background: #252526; color: #ccc;"
    "  gridline-color: #3a3a3a; border: 1px solid #3a3a3a;"
    "  font-family: Consolas; font-size: 12px;"
    "}"
    "QHeaderView::section {"
    "  background: #2d2d2d; color: #aaa;"
    "  padding: 4px 8px; border: none; border-right: 1px solid #3a3a3a;"
    "}"
    "QTableWidget::item:selected { background: #094771; color: #fff; }"
    "QPushButton {"
    "  font-size: 13px; padding: 6px 18px;"
    "  background: #444; color: #ccc; border: none; border-radius: 3px;"
    "}"
    "QPushButton:hover { background: #555; }"
)


class EnvCheckWorker(QThread):
    """后台跑 check_all()，每完成一项 emit 一次。"""

    item_done = Signal(object)  # EnvResult

    def run(self) -> None:
        for result in check_all():
            if self.isInterruptionRequested():
                return
            self.item_done.emit(result)


class EnvCheckDialog(QDialog):
    """6 行表格：名称 · 状态 · 版本 · 路径。检测期间显示"检测中..."。"""

    COLUMNS = ["名称", "状态", "版本", "路径"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("环境检测")
        self.resize(720, 280)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._table = QTableWidget(len(ENV_SPECS), len(self.COLUMNS), self)
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # 预填名称 + "检测中..."，给用户即时反馈
        for row, spec in enumerate(ENV_SPECS):
            self._table.setItem(row, 0, QTableWidgetItem(spec.name))
            self._table.setItem(row, 1, QTableWidgetItem("检测中..."))
            self._table.setItem(row, 2, QTableWidgetItem(""))
            self._table.setItem(row, 3, QTableWidgetItem(""))
        layout.addWidget(self._table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 启动 worker
        self._worker = EnvCheckWorker(self)
        self._worker.item_done.connect(self._on_item_done)
        self._worker.start()

    def _on_item_done(self, result: EnvResult) -> None:
        # 通过 name 找到行号，避免依赖检测顺序
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, 0)
            if cell is not None and cell.text() == result.name:
                self._fill_row(row, result)
                return

    def _fill_row(self, row: int, result: EnvResult) -> None:
        if not result.installed:
            self._set_cell(row, 1, "✗ 未安装")
            self._set_cell(row, 2, "-")
            self._set_cell(row, 3, "-")
            return
        if result.error:
            self._set_cell(row, 1, "⚠ 异常")
            self._set_cell(row, 2, result.error)
        else:
            self._set_cell(row, 1, "✓ 已安装")
            self._set_cell(row, 2, result.version or "未知")
        self._set_cell(row, 3, result.path or "")

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self._table.setItem(row, col, item)

    def closeEvent(self, event) -> None:
        # worker 还在跑时请求中断并等待，避免 thread destroyed 警告
        if self._worker.isRunning():
            self._worker.requestInterruption()
            # 子进程 timeout 是 3s，最坏情况下当前一项还要等几秒；给 4s 兜底
            self._worker.wait(4000)
        super().closeEvent(event)
