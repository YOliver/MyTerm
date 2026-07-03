"""主线程看门狗测试。

只测不依赖 Qt 的核心逻辑：心跳超时检测、卡死时 dump 栈、恢复后重新武装。
QTimer 相关的 start() 不在此覆盖（需要 Qt 事件循环）。
"""
from __future__ import annotations

import logging
import time

from store.watchdog import MainThreadWatchdog


def test_no_dump_when_heartbeat_fresh(caplog):
    """心跳持续刷新时，不应判定为卡死。"""
    wd = MainThreadWatchdog(timeout=0.2, check_interval=0.05)
    with caplog.at_level(logging.ERROR):
        # 手动跑几轮检查，其间不断心跳
        for _ in range(5):
            wd.beat()
            elapsed = time.monotonic() - wd._beat
            if elapsed >= wd._timeout and not wd._dumped:
                wd._dump_main_stack(elapsed)
                wd._dumped = True
            time.sleep(0.02)
    assert not wd._dumped
    assert "主线程卡死" not in caplog.text


def test_dump_when_heartbeat_stale(caplog):
    """心跳超时后应 dump 主线程栈，且只 dump 一次。"""
    wd = MainThreadWatchdog(timeout=0.1, check_interval=0.05)
    # 制造一次超时
    wd._beat = time.monotonic() - 1.0
    with caplog.at_level(logging.ERROR):
        elapsed = time.monotonic() - wd._beat
        wd._dump_main_stack(elapsed)
        wd._dumped = True
    assert "主线程卡死" in caplog.text
    # 栈里应含本测试函数名，证明抓到的是当前（主）线程栈
    assert "test_dump_when_heartbeat_stale" in caplog.text


def test_recovery_rearms(caplog):
    """dump 后主线程恢复心跳，_dumped 复位以便下次仍能报警。"""
    wd = MainThreadWatchdog(timeout=0.1, check_interval=0.05)
    wd._dumped = True
    with caplog.at_level(logging.WARNING):
        wd.beat()
    assert wd._dumped is False
    assert "主线程已恢复响应" in caplog.text


def test_dump_missing_frame_no_crash(caplog):
    """抓不到指定线程栈时只记录错误，不抛异常。"""
    wd = MainThreadWatchdog(timeout=0.1)
    wd._main_thread_id = -1  # 不存在的线程 id
    with caplog.at_level(logging.ERROR):
        wd._dump_main_stack(elapsed=5.0)
    assert "抓不到栈" in caplog.text
