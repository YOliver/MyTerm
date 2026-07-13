"""CLI 安装对话框：左侧列表 + 右侧实时日志。

布局：

    +-------------------------------+--------------------------------+
    | [Claude Code  ✓ 已安装 1.0.x] | 描述 / 依赖                    |
    | [其它 CLI     ○ 未安装]       | 日志窗口（QPlainTextEdit）     |
    | ...                           | ...                            |
    |                               | [主按钮] [次按钮] [关闭]       |
    +-------------------------------+--------------------------------+

按钮策略（按当前选中行的安装状态切换）：
- 未安装    → 主"安装"
- 已安装    → 主"卸载"（红） + 次"重新安装"
- 任务进行中 → 主按钮文案变 "安装中..."/"卸载中..."，全部 disabled

线程模型：
- 打开时启动 ``DetectWorker``（QThread），逐项调 ``spec.detect()``，每完成
  一项 emit 一次结果，主线程刷新对应行的状态文本。
- 用户点主/次按钮时启动 ``InstallWorker``（QThread），消费 ``install()`` 或
  ``uninstall()`` 生成器，逐条 emit InstallEvent 给主线程。

中断保护：closeEvent 里对所有 worker 都 requestInterruption + wait，
避免 thread destroyed 警告。
"""
from __future__ import annotations

from typing import Callable, Iterator, Literal

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from scripts.cli_installers._base import InstallEvent
from store.cli_installers import InstallerSpec, discover
from store.shell_presets import (
    add_for_installer, load as load_presets, remove_for_installer, save as save_presets,
)


# 任务种类：跑安装还是跑卸载，决定日志开头/结尾的文案
TaskKind = Literal["install", "uninstall"]


_DIALOG_STYLE = (
    "QDialog { background: #1e1e1e; }"
    "QLabel { color: #ccc; }"
    "QListWidget {"
    "  background: #252526; color: #ccc;"
    "  border: 1px solid #3a3a3a;"
    "  font-family: Consolas; font-size: 12px;"
    "  outline: none;"
    "}"
    "QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #2a2a2a; }"
    "QListWidget::item:selected { background: #094771; color: #fff; }"
    "QListWidget::item:hover { background: #2a2d2e; }"
    "QPlainTextEdit {"
    "  background: #1e1e1e; color: #ddd;"
    "  border: 1px solid #3a3a3a;"
    "  font-family: Consolas; font-size: 12px;"
    "}"
    "QPushButton {"
    "  font-size: 13px; padding: 6px 18px;"
    "  background: #444; color: #ccc; border: none; border-radius: 3px;"
    "}"
    "QPushButton:hover { background: #555; }"
    "QPushButton:disabled { background: #333; color: #666; }"
    "QPushButton#primary { background: #0e639c; color: #fff; }"
    "QPushButton#primary:hover { background: #1177bb; }"
    "QPushButton#primary:disabled { background: #2a4a66; color: #888; }"
    "QPushButton#danger { background: #a1260d; color: #fff; }"
    "QPushButton#danger:hover { background: #c42b1c; }"
    "QPushButton#danger:disabled { background: #4a1f17; color: #888; }"
    "QSplitter::handle { background: #2d2d2d; }"
)


class DetectWorker(QThread):
    """后台串行调用每个 spec 的 detect()，每完成一项 emit 一次。"""

    item_done = Signal(str, bool, str)  # (spec_id, installed, detail)

    def __init__(self, specs: list[InstallerSpec], parent=None) -> None:
        super().__init__(parent)
        self._specs = specs

    def run(self) -> None:
        for spec in self._specs:
            if self.isInterruptionRequested():
                return
            try:
                installed, detail = spec.detect()
            except Exception as e:  # noqa: BLE001 — 第三方脚本可能抛任何错
                installed, detail = False, f"detect 异常: {e}"
            self.item_done.emit(spec.id, bool(installed), str(detail))


class InstallWorker(QThread):
    """后台跑某个生成器（install 或 uninstall），逐条 emit 事件。

    名字保留 ``InstallWorker`` 历史命名——内部对装/卸两条路径完全对称，
    没必要为了改名再加一个等价类型。
    """

    event = Signal(object)  # InstallEvent

    def __init__(
        self,
        factory: Callable[[], Iterator[InstallEvent]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._factory = factory

    def run(self) -> None:
        try:
            for ev in self._factory():
                if self.isInterruptionRequested():
                    return
                self.event.emit(ev)
        except Exception as e:  # noqa: BLE001
            self.event.emit(InstallEvent("stderr", f"脚本异常: {e}"))
            self.event.emit(InstallEvent("exit", "", returncode=1))


class CliInstallDialog(QDialog):
    """CLI 安装对话框。

    构造时调 ``discover()`` 拿安装项；可通过 ``specs`` 参数注入（测试用）。

    ``presets_changed`` 信号：在安装/卸载成功且联动写入 shell_presets.json 后发出，
    供 MainWindow 重新 ``load()`` 预设刷新启动下拉框。无参——监听方自己重读即可。
    """

    presets_changed = Signal()

    def __init__(
        self,
        parent=None,
        specs: list[InstallerSpec] | None = None,
        store=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("CLI 安装")
        self.resize(820, 480)
        self.setStyleSheet(_DIALOG_STYLE)
        self._store = store  # DataStore 实例（可选，兼容旧调用）

        self._specs: list[InstallerSpec] = specs if specs is not None else discover()
        self._detect_worker: DetectWorker | None = None
        self._install_worker: InstallWorker | None = None
        # 当前正在跑的任务：spec id + 类型（install/uninstall）。
        # 非 None 表示有任务进行中，关闭对话框时要先打断。
        self._busy_id: str | None = None
        self._busy_kind: TaskKind | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        if not self._specs:
            outer.addWidget(QLabel("未发现任何 CLI 安装脚本。"))
            self._add_close_only(outer)
            return

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        outer.addWidget(splitter, 1)

        # 左：CLI 列表
        self._list = QListWidget(self)
        self._list.setMinimumWidth(260)
        for spec in self._specs:
            item = QListWidgetItem(self._format_item_text(spec, "检测中..."))
            item.setData(Qt.ItemDataRole.UserRole, spec.id)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        # 右：详情 + 日志
        right = QWidget(self)
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(6)

        self._desc_label = QLabel("", self)
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet("color: #aaa; font-size: 12px;")
        rlay.addWidget(self._desc_label)

        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)  # 防止极端日志爆内存
        rlay.addWidget(self._log, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # 底部按钮：主按钮（安装/卸载）+ 次按钮（重新安装，仅已装时显示）+ 关闭
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        # 次按钮放在主按钮左边，视觉上"次要操作 < 主要操作 < 关闭"
        self._secondary_btn = QPushButton("重新安装", self)
        self._secondary_btn.clicked.connect(self._on_secondary_clicked)
        self._secondary_btn.setVisible(False)
        btn_row.addWidget(self._secondary_btn)
        self._primary_btn = QPushButton("安装", self)
        self._primary_btn.setObjectName("primary")
        self._primary_btn.clicked.connect(self._on_primary_clicked)
        btn_row.addWidget(self._primary_btn)
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        outer.addLayout(btn_row)

        # 默认选中第一项 + 启动检测
        self._list.setCurrentRow(0)
        self._start_detect()

    # ---- 辅助：空列表场景的简化布局 ----
    def _add_close_only(self, outer: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addStretch()
        btn = QPushButton("关闭", self)
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        outer.addLayout(row)

    # ---- 列表渲染 ----
    @staticmethod
    def _format_item_text(spec: InstallerSpec, status: str) -> str:
        return f"{spec.name}\n  {status}"

    def _spec_by_id(self, spec_id: str) -> InstallerSpec | None:
        for s in self._specs:
            if s.id == spec_id:
                return s
        return None

    def _row_by_id(self, spec_id: str) -> int:
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == spec_id:
                return i
        return -1

    # ---- 检测流程 ----
    def _start_detect(self) -> None:
        self._detect_worker = DetectWorker(self._specs, self)
        self._detect_worker.item_done.connect(self._on_detected)
        self._detect_worker.start()

    def _on_detected(self, spec_id: str, installed: bool, detail: str) -> None:
        spec = self._spec_by_id(spec_id)
        if spec is None:
            return
        row = self._row_by_id(spec_id)
        if row < 0:
            return
        if installed:
            status = f"✓ 已安装  {detail}" if detail else "✓ 已安装"
        else:
            status = f"○ 未安装" + (f"  {detail}" if detail else "")
        item = self._list.item(row)
        if item is not None:
            item.setText(self._format_item_text(spec, status))
        # 当前行刚好是这个 spec → 同步刷新按钮文本
        if self._list.currentRow() == row:
            self._refresh_buttons(installed)

    # ---- 选中切换 ----
    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._specs):
            return
        spec = self._specs[row]
        requires = "、".join(spec.requires) if spec.requires else "无"
        self._desc_label.setText(f"{spec.description}\n依赖：{requires}")
        # 切换条目时清空日志（只保留当前条目的输出）
        # 例外：当前正在跑任务的就是这个条目时，保留日志
        if self._busy_id != spec.id:
            self._log.clear()
        # 默认按钮文案：根据当前显示的状态文本判断
        item = self._list.item(row)
        installed = bool(item and "✓" in item.text())
        self._refresh_buttons(installed)

    def _refresh_buttons(self, installed: bool) -> None:
        """根据 (installed, busy) 状态刷新主/次按钮的文案与可点击性。

        这是 UI 状态机的唯一入口——任何状态变化（detect 完成、点击启动、
        任务结束）都通过它来同步 UI，避免分散的 setText/setEnabled 调用打架。
        """
        spec = self._current_spec()
        has_uninstall = spec is not None and spec.uninstall is not None

        # busy 分支：所有按钮 disabled，主按钮显示进行中文案
        if self._busy_id is not None:
            kind = self._busy_kind
            self._primary_btn.setText("卸载中..." if kind == "uninstall" else "安装中...")
            self._primary_btn.setEnabled(False)
            self._secondary_btn.setEnabled(False)
            # busy 时次按钮的可见性维持 detect 完成时的样子，不动
            return

        if installed:
            # 已装：主按钮"卸载"（红），次按钮"重新安装"
            self._primary_btn.setText("卸载")
            self._primary_btn.setObjectName("danger")
            self._primary_btn.setEnabled(has_uninstall)
            self._secondary_btn.setText("重新安装")
            self._secondary_btn.setVisible(True)
            self._secondary_btn.setEnabled(True)
        else:
            # 未装：仅"安装"
            self._primary_btn.setText("安装")
            self._primary_btn.setObjectName("primary")
            self._primary_btn.setEnabled(True)
            self._secondary_btn.setVisible(False)

        # objectName 改了之后必须重新 polish 才能让 QSS 重新匹配
        self._primary_btn.style().unpolish(self._primary_btn)
        self._primary_btn.style().polish(self._primary_btn)

    def _current_spec(self) -> InstallerSpec | None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._specs):
            return None
        return self._specs[row]

    # ---- 点击：路由到 install/uninstall ----
    def _on_primary_clicked(self) -> None:
        """已装态点的是"卸载"，未装态点的是"安装"——按当前文案路由。"""
        if self._busy_id is not None:
            return
        spec = self._current_spec()
        if spec is None:
            return
        if self._primary_btn.text() == "卸载":
            self._start_task(spec, "uninstall")
        else:
            self._start_task(spec, "install")

    def _on_secondary_clicked(self) -> None:
        """次按钮目前只有"重新安装"一种语义。"""
        if self._busy_id is not None:
            return
        spec = self._current_spec()
        if spec is None:
            return
        self._start_task(spec, "install")

    # ---- 任务启动（install/uninstall 共用入口） ----
    def _start_task(self, spec: InstallerSpec, kind: TaskKind) -> None:
        if self._install_worker is not None and self._install_worker.isRunning():
            return  # 防抖：已有任务跑就忽略

        if kind == "uninstall":
            if spec.uninstall is None:
                return  # 理论上按钮已 disabled，兜底再挡一次
            # 卸载不可逆，弹二次确认
            ans = QMessageBox.question(
                self,
                "确认卸载",
                f"确定要卸载 {spec.name} 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            factory = spec.uninstall
            verb = "卸载"
        else:
            factory = spec.install
            verb = "安装"

        self._log.clear()
        self._log.appendPlainText(f"==> 准备{verb} {spec.name}")
        self._busy_id = spec.id
        self._busy_kind = kind
        # 刷新按钮显示进行中状态。installed 参数此处不影响（busy 分支提前 return）
        self._refresh_buttons(installed=False)

        self._install_worker = InstallWorker(factory, self)
        self._install_worker.event.connect(self._on_task_event)
        self._install_worker.start()

    def _on_task_event(self, ev: InstallEvent) -> None:
        if ev.kind == "exit":
            ok = ev.returncode == 0
            kind = self._busy_kind
            verb = "卸载" if kind == "uninstall" else "安装"
            tail = f"✓ {verb}成功" if ok else f"✗ {verb}失败 (returncode={ev.returncode})"
            self._log.appendPlainText("")
            self._log.appendPlainText(tail)
            # 任务成功才动预设；失败时维持现状，避免"装一半进了下拉框但其实跑不起来"
            busy_spec_id = self._busy_id
            # 清空 busy 状态 + 重新检测当前条目刷新行/按钮
            self._busy_id = None
            self._busy_kind = None
            if ok and busy_spec_id is not None:
                self._sync_presets_after(busy_spec_id, kind)
            self._rerun_detect_for_current()
            return

        prefix = ""
        if ev.kind == "stderr":
            prefix = "[err] "
        elif ev.kind == "info":
            prefix = "==> "
        self._log.appendPlainText(f"{prefix}{ev.text}")

    def _sync_presets_after(self, spec_id: str, kind: TaskKind | None) -> None:
        """安装/卸载成功后联动 shell_presets.json，并 emit ``presets_changed``。

        失败/异常路径（IO 错、launch 元数据缺失）不抛——把日志打到对话框里
        即可，主流程已经成功了，没必要因为预设落盘问题让用户看见 traceback。
        """
        spec = self._spec_by_id(spec_id)
        if spec is None:
            return

        try:
            current = load_presets(store=self._store) if self._store else load_presets()
        except Exception as e:  # noqa: BLE001
            self._log.appendPlainText(f"[err] 读取 shell_presets 失败：{e}")
            return

        if kind == "install":
            if spec.launch is None:
                # 模块没声明 LAUNCH，不联动；这是合法情况（部分 CLI 用户自己决定怎么启动）
                return
            new_list, changed = add_for_installer(current, spec.id, spec.launch)
            if not changed:
                return
            action_log = f"==> 已将 {spec.name} 加入启动预设"
        elif kind == "uninstall":
            new_list, changed = remove_for_installer(current, spec.id)
            if not changed:
                return
            action_log = f"==> 已从启动预设移除 {spec.name}"
        else:
            return

        try:
            if self._store:
                save_presets(new_list, store=self._store)
            else:
                save_presets(new_list)
        except Exception as e:  # noqa: BLE001
            self._log.appendPlainText(f"[err] 写入 shell_presets 失败：{e}")
            return

        self._log.appendPlainText(action_log)
        self.presets_changed.emit()

    def _rerun_detect_for_current(self) -> None:
        """安装/卸载完成后，仅对当前选中条目跑一次 detect 来刷新行状态。

        不复用 DetectWorker（它跑全表），单独起一个轻量 QThread 太重；
        直接同步调一次也可以——detect 自带 3s 超时，主线程被阻塞最多 3s。
        Qt 事件循环虽然会卡 3s，但用户刚操作完就盯着结果，影响可接受，
        简化实现优先于极致体验。
        """
        spec = self._current_spec()
        if spec is None:
            return
        try:
            installed, detail = spec.detect()
        except Exception as e:  # noqa: BLE001
            installed, detail = False, f"detect 异常: {e}"
        self._on_detected(spec.id, installed, detail)

    # ---- 关闭：打断后台线程 ----
    def closeEvent(self, event) -> None:
        for w in (self._detect_worker, self._install_worker):
            if w is not None and w.isRunning():
                w.requestInterruption()
                w.wait(4000)
        super().closeEvent(event)

    # ---- 提示用：用户主动关闭但任务还在跑时给确认 ----
    def reject(self) -> None:
        # 用户按 Esc 也走这里。任务进行中给个二次确认。
        if self._busy_id is not None:
            verb = "卸载" if self._busy_kind == "uninstall" else "安装"
            ans = QMessageBox.question(
                self,
                f"{verb}进行中",
                f"{verb}尚未结束，确定关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        super().reject()
