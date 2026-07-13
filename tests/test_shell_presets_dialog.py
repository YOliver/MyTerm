"""设置面板 ``ShellPresetsDialog`` 的关键交互测试。

只覆盖核心：
- 初始化时 readonly/installer_id 元数据被读入
- 选中 readonly 行时"删除"按钮被禁用
- 保存时 readonly/installer_id 字段透传，不会丢失
"""
from __future__ import annotations

import pytest

from store.shell_presets import ShellPreset


def test_dialog_disables_delete_for_readonly_row(qapp):
    from ui.shell_presets_dialog import ShellPresetsDialog

    presets = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("自定义", "powershell", "echo hi"),
    ]
    dlg = ShellPresetsDialog(presets)
    try:
        # 默认选中第 0 行（readonly）→ 删除应禁用
        assert dlg._table.currentRow() == 0
        assert not dlg._btn_remove.isEnabled()

        # 切到第 1 行（普通项）→ 删除应启用
        dlg._table.selectRow(1)
        qapp.processEvents()
        assert dlg._btn_remove.isEnabled()
    finally:
        dlg.close()


def test_dialog_keeps_readonly_and_installer_id_when_saving(qapp, monkeypatch):
    """保存时 presets_changed 信号携带完整的 readonly/installer_id 元数据。"""
    from ui import shell_presets_dialog as dlg_module
    from ui.shell_presets_dialog import ShellPresetsDialog

    initial = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("Claude Code", "cmd", "claude", installer_id="claude_code"),
        ShellPreset("custom", "powershell", "echo hi"),
    ]
    dlg = ShellPresetsDialog(initial)
    received = []
    dlg.presets_changed.connect(lambda lst: received.append(lst))
    try:
        dlg._on_save()

        # presets_changed 信号携带完整元数据
        assert len(received) == 1
        out = received[0]
        by_label = {p.label: p for p in out}
        assert by_label["powershell"].readonly is True
        assert by_label["Claude Code"].installer_id == "claude_code"
        assert by_label["custom"].readonly is False
        assert by_label["custom"].installer_id is None
    finally:
        dlg.close()


def test_dialog_remove_blocked_on_readonly_even_if_called_directly(qapp):
    """``_on_remove`` 直接调用也要拦住 readonly 行——按钮禁用是 UI 兜底，逻辑层也要兜。"""
    from ui.shell_presets_dialog import ShellPresetsDialog

    presets = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("custom", "powershell", "echo hi"),
    ]
    dlg = ShellPresetsDialog(presets)
    try:
        dlg._table.selectRow(0)  # readonly 行
        dlg._on_remove()
        # 行数没变
        assert dlg._table.rowCount() == 2
    finally:
        dlg.close()
