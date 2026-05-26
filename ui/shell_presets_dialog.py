"""「设置 → AI CLI 配置」对话框：维护 ``shell_presets.json``。

3 列表格：标签 / 宿主（下拉）/ 命令；右侧增删上下移；底部保存/取消。

保存时把表格收集成 ``list[ShellPreset]``，调 ``shell_presets.save()`` 落盘，
emit ``presets_changed`` 信号让 ``MainWindow`` 自己刷新启动下拉框；已开终端不动。

样式直接复用 ``env_check_dialog._DIALOG_STYLE`` + 一段增量（QComboBox/主按钮）
避免改动 env_check_dialog 引发漂移。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from store import shell_presets
from store.shell_presets import VALID_HOSTS, ShellPreset
from ui.env_check_dialog import _DIALOG_STYLE


# 增量样式：补充 QComboBox（host 列下拉）与主按钮变体（保存）。
# 与 env_check_dialog._DIALOG_STYLE 拼接使用，避免互相依赖。
_EXTRA_STYLE = (
    "QLabel { color: #ccc; font-size: 12px; }"
    "QComboBox {"
    "  background: #1e1e1e; color: #ccc; border: 1px solid #555; border-radius: 3px;"
    "  padding: 2px 8px; font-family: Consolas; font-size: 12px;"
    "}"
    "QComboBox:hover { border-color: #777; }"
    "QComboBox QAbstractItemView {"
    "  background: #252526; color: #ccc; border: 1px solid #555;"
    "  selection-background-color: #094771; selection-color: #fff;"
    "}"
    "QPushButton#primary {"
    "  background: #0e639c; color: #fff; padding: 6px 18px;"
    "  border: none; border-radius: 3px; font-size: 13px;"
    "}"
    "QPushButton#primary:hover { background: #1177bb; }"
    "QPushButton#primary:pressed { background: #094771; }"
)


class ShellPresetsDialog(QDialog):
    """编辑启动下拉框预设的对话框。保存后通过 ``presets_changed`` 通知父窗口。"""

    presets_changed = Signal(list)  # list[ShellPreset]

    COLUMNS = ["标签", "宿主", "命令"]

    def __init__(self, current_presets: list[ShellPreset], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AI CLI 配置")
        self.resize(720, 380)
        self.setStyleSheet(_DIALOG_STYLE + _EXTRA_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = QLabel("管理启动下拉框中的 shell / CLI 预设。"
                      "宿主 powershell / cmd 会自动加 -NoExit / /K；"
                      "宿主 none 表示命令本身就是要直接启动的 exe。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        body = QHBoxLayout()
        body.setSpacing(8)

        # ---- 表格 ----
        self._table = QTableWidget(0, len(self.COLUMNS), self)
        self._table.setHorizontalHeaderLabels(self.COLUMNS)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        body.addWidget(self._table, 1)

        # ---- 右侧按钮列 ----
        side = QVBoxLayout()
        side.setSpacing(6)
        self._btn_add = QPushButton("新增", self)
        self._btn_remove = QPushButton("删除", self)
        self._btn_up = QPushButton("↑ 上移", self)
        self._btn_down = QPushButton("↓ 下移", self)
        for b in (self._btn_add, self._btn_remove, self._btn_up, self._btn_down):
            b.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            side.addWidget(b)
        side.addStretch()
        body.addLayout(side)

        layout.addLayout(body, 1)

        # ---- 底部 保存/取消 ----
        bottom = QHBoxLayout()
        bottom.addStretch()
        self._btn_save = QPushButton("保存", self)
        self._btn_save.setObjectName("primary")
        self._btn_cancel = QPushButton("取消", self)
        bottom.addWidget(self._btn_save)
        bottom.addWidget(self._btn_cancel)
        layout.addLayout(bottom)

        # ---- 信号 ----
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_up.clicked.connect(lambda: self._move_row(-1))
        self._btn_down.clicked.connect(lambda: self._move_row(+1))
        self._btn_save.clicked.connect(self._on_save)
        self._btn_cancel.clicked.connect(self.reject)
        self._table.itemSelectionChanged.connect(self._refresh_buttons)

        # ---- 初始数据 ----
        for preset in current_presets:
            self._append_row(
                preset.label, preset.host, preset.raw_command,
                readonly=preset.readonly, installer_id=preset.installer_id,
            )
        if self._table.rowCount() > 0:
            self._table.selectRow(0)
        self._refresh_buttons()

    # ---------------- 行操作 ----------------

    def _append_row(
        self,
        label: str,
        host: str,
        command: str,
        readonly: bool = False,
        installer_id: str | None = None,
    ) -> None:
        row = self._table.rowCount()
        self._insert_row(row, label, host, command, readonly, installer_id)

    def _insert_row(
        self,
        row: int,
        label: str,
        host: str,
        command: str,
        readonly: bool = False,
        installer_id: str | None = None,
    ) -> None:
        self._table.insertRow(row)
        label_item = QTableWidgetItem(label)
        # readonly + installer_id 是行级元数据，附在第 0 列 item 的 UserRole 上：
        # 不影响显示，但保存时能取出来回写到 ShellPreset，避免丢字段。
        # 用一个 dict 而不是两个 role 编号，方便未来再加字段。
        label_item.setData(Qt.ItemDataRole.UserRole, {
            "readonly": bool(readonly),
            "installer_id": installer_id,
        })
        self._table.setItem(row, 0, label_item)

        combo = QComboBox()
        combo.addItems(VALID_HOSTS)
        if host in VALID_HOSTS:
            combo.setCurrentText(host)
        self._table.setCellWidget(row, 1, combo)

        self._table.setItem(row, 2, QTableWidgetItem(command))

    def _row_meta(self, row: int) -> dict:
        """读取第 0 列的元数据 dict，缺失/异常都视作"用户手加的非 readonly 项"。"""
        item = self._table.item(row, 0)
        if item is None:
            return {"readonly": False, "installer_id": None}
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            return data
        return {"readonly": False, "installer_id": None}

    def _current_row(self) -> int:
        return self._table.currentRow()

    def _on_add(self) -> None:
        cur = self._current_row()
        target = cur + 1 if cur >= 0 else self._table.rowCount()
        self._insert_row(target, "新预设", "powershell", "")
        self._table.selectRow(target)
        # 自动进入第 0 列编辑，提升新增手感
        item = self._table.item(target, 0)
        if item is not None:
            self._table.editItem(item)

    def _on_remove(self) -> None:
        cur = self._current_row()
        if cur < 0:
            return
        # readonly 项保护：内置的 powershell/cmd 或 installer 添加的项不允许删除。
        # 卸载 installer 才是清理它的正确路径；让它从这里被删掉等于让用户失去
        # 自动同步能力。按钮已在 _refresh_buttons 里 disable 了，这里再兜一层。
        if self._row_meta(cur).get("readonly"):
            return
        if self._table.rowCount() <= 1:
            QMessageBox.information(self, "提示", "至少保留一条预设")
            return
        self._table.removeRow(cur)
        # 选择保持在原位置（或最后一行）
        new_cur = min(cur, self._table.rowCount() - 1)
        if new_cur >= 0:
            self._table.selectRow(new_cur)

    def _move_row(self, delta: int) -> None:
        cur = self._current_row()
        if cur < 0:
            return
        target = cur + delta
        if not (0 <= target < self._table.rowCount()):
            return

        # 收集两行数据再交换。cellWidget(QComboBox) 不能 takeItem，所以读 currentText 重建。
        # 元数据（readonly/installer_id）也要一起搬，否则换位后内置项就丢失保护标记。
        cur_data = self._row_to_tuple(cur)
        cur_meta = self._row_meta(cur)
        target_data = self._row_to_tuple(target)
        target_meta = self._row_meta(target)

        self._write_row(cur, *target_data, meta=target_meta)
        self._write_row(target, *cur_data, meta=cur_meta)
        self._table.selectRow(target)

    def _row_to_tuple(self, row: int) -> tuple[str, str, str]:
        label_item = self._table.item(row, 0)
        cmd_item = self._table.item(row, 2)
        combo = self._table.cellWidget(row, 1)
        label = label_item.text() if label_item else ""
        host = combo.currentText() if isinstance(combo, QComboBox) else "none"
        cmd = cmd_item.text() if cmd_item else ""
        return label, host, cmd

    def _write_row(
        self,
        row: int,
        label: str,
        host: str,
        command: str,
        meta: dict | None = None,
    ) -> None:
        self._table.item(row, 0).setText(label)
        if meta is not None:
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, dict(meta))
        self._table.item(row, 2).setText(command)
        combo = self._table.cellWidget(row, 1)
        if isinstance(combo, QComboBox):
            combo.setCurrentText(host)

    def _refresh_buttons(self) -> None:
        cur = self._current_row()
        rows = self._table.rowCount()
        is_readonly = cur >= 0 and self._row_meta(cur).get("readonly", False)
        # 删除按钮：readonly 行禁用（其它操作仍允许，比如改 label/调整顺序）
        self._btn_remove.setEnabled(cur >= 0 and rows > 1 and not is_readonly)
        self._btn_up.setEnabled(cur > 0)
        self._btn_down.setEnabled(0 <= cur < rows - 1)

    # ---------------- 保存 ----------------

    def _collect_presets(self) -> list[ShellPreset] | None:
        """收集表格成 list[ShellPreset]；遇到非法返回 None 并提示用户。"""
        result: list[ShellPreset] = []
        seen_labels: set[str] = set()
        for row in range(self._table.rowCount()):
            label, host, command = self._row_to_tuple(row)
            label = label.strip()
            command = command.strip()
            if not label:
                self._warn(f"第 {row + 1} 行的标签不能为空")
                self._table.selectRow(row)
                return None
            if not command:
                self._warn(f"第 {row + 1} 行（{label}）的命令不能为空")
                self._table.selectRow(row)
                return None
            if host not in VALID_HOSTS:
                # 理论上 QComboBox 不会出非法值，但兜一层防御
                self._warn(f"第 {row + 1} 行（{label}）的宿主非法")
                return None
            if label in seen_labels:
                # 重名只警告，不阻塞：label 仅用于显示+回填，重了不会崩
                pass
            seen_labels.add(label)
            meta = self._row_meta(row)
            result.append(ShellPreset(
                label=label, host=host, raw_command=command,
                readonly=bool(meta.get("readonly", False)),
                installer_id=meta.get("installer_id"),
            ))
        if not result:
            self._warn("至少需要一条预设")
            return None
        return result

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "无法保存", msg)

    def _on_save(self) -> None:
        presets = self._collect_presets()
        if presets is None:
            return
        shell_presets.save(presets)
        self.presets_changed.emit(presets)
        self.accept()
