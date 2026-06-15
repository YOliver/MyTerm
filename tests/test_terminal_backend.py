"""TerminalBackend.stop() 容错测试。

休眠唤醒后 winpty 句柄进入僵死状态，read() 既不返回也不抛异常，导致
线程永远卡在 PtyProcess.read()。stop() 必须在 wait 超时后调用 terminate()
强制终止，否则槽位虽被释放但 QThread 仍在跑、连带主线程 UI 异常
（见 myterm.log 2026-06-03 10:56 复现）。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.terminal_backend import TerminalBackend


@pytest.fixture
def backend(qapp):
    """构造一个未真正 spawn 的 backend：只测 stop() 行为，不需要真子进程。"""
    b = TerminalBackend()
    # 假装持有一个进程对象，stop() 会调 close()/isalive()
    fake_proc = MagicMock()
    fake_proc.pid = 12345
    fake_proc.isalive.return_value = True
    b._process = fake_proc
    yield b


def test_stop_normal_path_does_not_terminate(backend):
    """正常情况下 wait 在 2s 内返回 True，不应触发 terminate。"""
    fake_proc = backend._process  # 保存引用，stop() 可能置 None
    with patch.object(backend, "wait", return_value=True) as mock_wait, \
         patch.object(backend, "terminate") as mock_terminate:
        backend.stop()
        # close() 必须被调（让 read 返回）
        fake_proc.close.assert_called_once()
        # wait 被调一次（2s 等线程自然退出）
        assert mock_wait.call_count == 1
        # 没卡住 → 不该 terminate
        mock_terminate.assert_not_called()


def test_stop_timeout_triggers_terminate(backend):
    """wait 超时 → 必须调 terminate 兜底，否则线程僵死。"""
    # 第一次 wait 返回 False（超时），第二次返回 True（terminate 后线程退了）
    fake_proc = backend._process  # 保存引用，stop() 可能置 None
    with patch.object(backend, "wait", side_effect=[False, True]) as mock_wait, \
         patch.object(backend, "terminate") as mock_terminate:
        backend.stop()
        fake_proc.close.assert_called_once()
        # wait 调用两次：一次 2s 等自然退出 + 一次 500ms 等 terminate 生效
        assert mock_wait.call_count == 2
        mock_terminate.assert_called_once()


def test_stop_terminate_also_fails_does_not_raise(backend):
    """terminate 后线程仍卡住，stop() 必须不抛异常（最坏情况只能放弃 + 记日志）。"""
    with patch.object(backend, "wait", side_effect=[False, False]), \
         patch.object(backend, "terminate"):
        # 不该抛任何异常
        backend.stop()


def test_stop_without_process_no_crash(qapp):
    """没 spawn 过 / 已 stop 过的 backend 再次调 stop 不应崩溃。"""
    b = TerminalBackend()
    # _process 仍是 None
    with patch.object(b, "wait", return_value=True):
        b.stop()  # 应安静返回，不抛
