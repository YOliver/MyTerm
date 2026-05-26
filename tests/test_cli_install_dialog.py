"""CLI 安装对话框 UI 行为测试。

通过依赖注入（``specs=`` 参数）绕过真实 ``discover()``，避免对环境依赖。
线程同步用 ``QThread.wait`` + ``processEvents``，与工程内其它 Qt 测试一致。
"""
from __future__ import annotations

import pytest

from scripts.cli_installers._base import InstallEvent
from store.cli_installers import InstallerSpec


def _make_spec(
    spec_id: str = "fake_cli",
    name: str = "Fake CLI",
    detect_result: tuple[bool, str] = (False, ""),
    install_events: list[InstallEvent] | None = None,
    uninstall_events: list[InstallEvent] | None = None,
    with_uninstall: bool = True,
    launch: dict | None = None,
) -> InstallerSpec:
    """构造一个可控的 InstallerSpec，用于注入对话框。

    ``with_uninstall=False`` → uninstall 字段为 None（模拟"不支持卸载"的脚本）。
    ``launch`` → 透传到 spec.launch；None 表示"该脚本不联动启动预设"。
    """
    if install_events is None:
        install_events = [
            InstallEvent("stdout", "installing..."),
            InstallEvent("exit", "", returncode=0),
        ]
    if uninstall_events is None:
        uninstall_events = [
            InstallEvent("stdout", "uninstalling..."),
            InstallEvent("exit", "", returncode=0),
        ]

    def _detect():
        return detect_result

    def _install():
        for ev in install_events:
            yield ev

    def _uninstall():
        for ev in uninstall_events:
            yield ev

    return InstallerSpec(
        id=spec_id,
        name=name,
        description="测试用假 CLI",
        requires=("npm",),
        detect=_detect,
        install=_install,
        uninstall=_uninstall if with_uninstall else None,
        launch=launch,
    )


def _drain_thread(worker, qapp, timeout_ms: int = 3000) -> None:
    """等 QThread 跑完并把信号都派发到主线程。

    Qt 的信号在跨线程时排队到接收线程的事件循环；测试里 qapp 主循环没在跑，
    需要手动 processEvents 才能让 connect 的槽真正执行。
    """
    if worker is None:
        return
    worker.wait(timeout_ms)
    qapp.processEvents()


# ----------------------------- 列表渲染 -----------------------------

def test_dialog_lists_all_specs(qapp):
    from ui.cli_install_dialog import CliInstallDialog

    specs = [_make_spec("a_cli", "Alpha CLI"), _make_spec("b_cli", "Beta CLI")]
    dlg = CliInstallDialog(specs=specs)
    try:
        # 列表条目数 == 注入的 spec 数
        assert dlg._list.count() == 2
        # 第一行被默认选中
        assert dlg._list.currentRow() == 0
        # 名字出现在文本中
        texts = [dlg._list.item(i).text() for i in range(2)]
        assert any("Alpha CLI" in t for t in texts)
        assert any("Beta CLI" in t for t in texts)
    finally:
        dlg.close()
        _drain_thread(dlg._detect_worker, qapp)


def test_dialog_empty_specs_renders_hint(qapp):
    """没有任何安装脚本时给出友好提示，不崩溃。"""
    from ui.cli_install_dialog import CliInstallDialog

    dlg = CliInstallDialog(specs=[])
    try:
        # 空列表分支根本不会创建 self._list
        assert not hasattr(dlg, "_list") or dlg._list.count() == 0
    finally:
        dlg.close()


# ----------------------------- 检测流程 -----------------------------

def test_dialog_detect_updates_row_status(qapp):
    """detect 返回已安装时，行文本含 ✓；主按钮文案变成"卸载"，次按钮显示"重新安装"。"""
    from ui.cli_install_dialog import CliInstallDialog

    spec = _make_spec(detect_result=(True, "1.0.123"))
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        # 给信号槽派发一次机会
        qapp.processEvents()

        item_text = dlg._list.item(0).text()
        assert "✓" in item_text
        assert "1.0.123" in item_text
        # 已装态：主按钮变卸载（红），次按钮显示"重新安装"。
        # Qt 的 isVisible() 在窗口未 show 时一律 False，用 isHidden() 反查
        # widget 自己记录的可见性标志（setVisible 设的就是它）。
        assert dlg._primary_btn.text() == "卸载"
        assert not dlg._secondary_btn.isHidden()
        assert dlg._secondary_btn.text() == "重新安装"
    finally:
        dlg.close()


def test_dialog_detect_unknown_status(qapp):
    """detect 返回未安装时，行显示 ○，主按钮"安装"，次按钮隐藏。"""
    from ui.cli_install_dialog import CliInstallDialog

    spec = _make_spec(detect_result=(False, ""))
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        assert "○" in dlg._list.item(0).text()
        assert dlg._primary_btn.text() == "安装"
        assert dlg._secondary_btn.isHidden()
    finally:
        dlg.close()


# ----------------------------- 安装流程 -----------------------------

def test_dialog_install_appends_log(qapp):
    """点击安装后，install() 生成器的事件被逐条追加到日志窗口。"""
    from ui.cli_install_dialog import CliInstallDialog

    events = [
        InstallEvent("info", "starting"),
        InstallEvent("stdout", "line-A"),
        InstallEvent("stdout", "line-B"),
        InstallEvent("exit", "", returncode=0),
    ]
    spec = _make_spec(install_events=events)
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        log_text = dlg._log.toPlainText()
        assert "line-A" in log_text
        assert "line-B" in log_text
        assert "starting" in log_text
        # 退出成功 → 末尾有成功标记
        assert "✓ 安装成功" in log_text
        # 安装完成后主按钮恢复可用
        assert dlg._primary_btn.isEnabled()
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


def test_dialog_install_failure_marks_failed(qapp):
    """install() 退出码非 0 时，日志末尾标"安装失败"。"""
    from ui.cli_install_dialog import CliInstallDialog

    events = [
        InstallEvent("stderr", "boom"),
        InstallEvent("exit", "", returncode=1),
    ]
    spec = _make_spec(install_events=events)
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        log_text = dlg._log.toPlainText()
        assert "[err] boom" in log_text
        assert "✗ 安装失败" in log_text
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


# ----------------------------- 卸载流程 -----------------------------

def test_dialog_uninstall_button_disabled_when_unsupported(qapp):
    """脚本未提供 uninstall 时，已装态的卸载按钮 disabled，避免用户点了没反应。"""
    from ui.cli_install_dialog import CliInstallDialog

    spec = _make_spec(detect_result=(True, "1.0.0"), with_uninstall=False)
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        # 文案还是"卸载"，但点不了——这个状态告诉用户"已装但本工具不支持卸载"
        assert dlg._primary_btn.text() == "卸载"
        assert not dlg._primary_btn.isEnabled()
        # 次按钮"重新安装"始终可用
        assert not dlg._secondary_btn.isHidden()
        assert dlg._secondary_btn.isEnabled()
    finally:
        dlg.close()


def test_dialog_uninstall_runs_when_confirmed(qapp, monkeypatch):
    """点卸载 → 确认 → uninstall() 事件流写入日志，结尾标"卸载成功"。"""
    from PySide6.QtWidgets import QMessageBox

    from ui.cli_install_dialog import CliInstallDialog

    # 拦截二次确认对话框，强制点 Yes
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )

    uninstall_events = [
        InstallEvent("info", "removing"),
        InstallEvent("stdout", "removed pkg"),
        InstallEvent("exit", "", returncode=0),
    ]
    spec = _make_spec(detect_result=(True, "1.0.0"), uninstall_events=uninstall_events)
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        # 已装态 → 主按钮是"卸载"，点击触发 uninstall 路径
        assert dlg._primary_btn.text() == "卸载"
        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        log_text = dlg._log.toPlainText()
        assert "removing" in log_text
        assert "removed pkg" in log_text
        assert "✓ 卸载成功" in log_text
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


def test_dialog_uninstall_aborted_when_user_says_no(qapp, monkeypatch):
    """二次确认点 No 时不启动 worker，日志保持空白。"""
    from PySide6.QtWidgets import QMessageBox

    from ui.cli_install_dialog import CliInstallDialog

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No
    )

    spec = _make_spec(detect_result=(True, "1.0.0"))
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        qapp.processEvents()

        # worker 没启动，日志为空，busy 标志位仍是 None
        assert dlg._install_worker is None
        assert dlg._log.toPlainText() == ""
        assert dlg._busy_id is None
    finally:
        dlg.close()


def test_dialog_secondary_triggers_install(qapp):
    """已装态点次按钮"重新安装"应跑 install()（不弹确认、不当卸载）。"""
    from ui.cli_install_dialog import CliInstallDialog

    install_events = [
        InstallEvent("stdout", "reinstall-line"),
        InstallEvent("exit", "", returncode=0),
    ]
    spec = _make_spec(detect_result=(True, "1.0.0"), install_events=install_events)
    dlg = CliInstallDialog(specs=[spec])
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_secondary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        log_text = dlg._log.toPlainText()
        assert "reinstall-line" in log_text
        # 走的是"安装"路径，结尾必须是"安装成功"而不是"卸载成功"
        assert "✓ 安装成功" in log_text
        assert "卸载" not in log_text or "准备卸载" not in log_text
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


# ----------------------------- 联动 shell_presets -----------------------------

def _patch_presets_io(monkeypatch, dlg_module, initial_presets):
    """把 dialog 用到的 load/save 替成内存版，避免动真实 %LOCALAPPDATA%。

    返回一个 list，存"被 save 写入的最后一份预设"，方便断言。
    """
    state = {"presets": list(initial_presets)}
    saved = []

    def fake_load():
        return list(state["presets"])

    def fake_save(presets):
        state["presets"] = list(presets)
        saved.append(list(presets))

    monkeypatch.setattr(dlg_module, "load_presets", fake_load)
    monkeypatch.setattr(dlg_module, "save_presets", fake_save)
    return saved, state


def test_dialog_install_success_appends_preset_and_emits_signal(qapp, monkeypatch):
    """安装成功 + spec.launch 非 None 时，往 shell_presets 加一条并 emit 信号。"""
    from ui import cli_install_dialog as dlg_module
    from store.shell_presets import default_presets

    saved, _state = _patch_presets_io(monkeypatch, dlg_module, default_presets())

    spec = _make_spec(
        spec_id="claude_code",
        launch={"label": "Claude Code", "host": "cmd", "raw_command": "claude"},
    )
    dlg = dlg_module.CliInstallDialog(specs=[spec])
    received = []
    dlg.presets_changed.connect(lambda: received.append(True))
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        # 写入了一份新的预设列表，包含 Claude Code
        assert len(saved) == 1
        labels = [p.label for p in saved[-1]]
        assert "Claude Code" in labels
        # 信号被 emit 了一次
        assert received == [True]
        # 日志里有"已加入启动预设"提示
        assert "已将 Fake CLI 加入启动预设" in dlg._log.toPlainText() \
            or "已将 Claude Code 加入启动预设" in dlg._log.toPlainText() \
            or "已将" in dlg._log.toPlainText()
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


def test_dialog_install_no_launch_does_not_touch_presets(qapp, monkeypatch):
    """spec.launch=None 时安装成功不动预设、不 emit 信号。"""
    from ui import cli_install_dialog as dlg_module
    from store.shell_presets import default_presets

    saved, _state = _patch_presets_io(monkeypatch, dlg_module, default_presets())

    spec = _make_spec(launch=None)
    dlg = dlg_module.CliInstallDialog(specs=[spec])
    received = []
    dlg.presets_changed.connect(lambda: received.append(True))
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        assert saved == []
        assert received == []
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


def test_dialog_install_failure_does_not_touch_presets(qapp, monkeypatch):
    """安装失败时不动预设——避免"装一半进了下拉框但其实跑不起来"。"""
    from ui import cli_install_dialog as dlg_module
    from store.shell_presets import default_presets

    saved, _state = _patch_presets_io(monkeypatch, dlg_module, default_presets())

    spec = _make_spec(
        install_events=[
            InstallEvent("stderr", "boom"),
            InstallEvent("exit", "", returncode=1),
        ],
        launch={"label": "X", "host": "cmd", "raw_command": "x"},
    )
    dlg = dlg_module.CliInstallDialog(specs=[spec])
    received = []
    dlg.presets_changed.connect(lambda: received.append(True))
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        assert saved == []
        assert received == []
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)


def test_dialog_uninstall_success_removes_preset(qapp, monkeypatch):
    """卸载成功后，shell_presets 中由该 installer 添加的项被移除并 emit 信号。"""
    from PySide6.QtWidgets import QMessageBox

    from ui import cli_install_dialog as dlg_module
    from store.shell_presets import ShellPreset, default_presets

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes
    )

    initial = default_presets() + [
        ShellPreset("Claude Code", "cmd", "claude", installer_id="claude_code"),
    ]
    saved, _state = _patch_presets_io(monkeypatch, dlg_module, initial)

    spec = _make_spec(
        spec_id="claude_code",
        detect_result=(True, "1.0.0"),
        launch={"label": "Claude Code", "host": "cmd", "raw_command": "claude"},
    )
    dlg = dlg_module.CliInstallDialog(specs=[spec])
    received = []
    dlg.presets_changed.connect(lambda: received.append(True))
    try:
        _drain_thread(dlg._detect_worker, qapp)
        qapp.processEvents()

        dlg._on_primary_clicked()
        _drain_thread(dlg._install_worker, qapp)
        qapp.processEvents()

        assert len(saved) == 1
        labels = [p.label for p in saved[-1]]
        assert "Claude Code" not in labels
        assert received == [True]
    finally:
        dlg.close()
        _drain_thread(dlg._install_worker, qapp)
