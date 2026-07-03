"""主线程看门狗：检测 UI 线程卡死并 dump 主线程调用栈。

用途：定位"点击启动无反应 / 界面完全卡死"类问题。

原理：
- 主线程通过 QTimer 周期性刷新心跳时间戳（``_beat``）。
- 一个后台守护线程周期性检查心跳，若距上次心跳超过 ``timeout`` 秒，
  说明主线程正卡在某个同步调用里（Qt 事件循环没机会执行 QTimer 回调），
  此时用 ``sys._current_frames()`` 抓取主线程的 Python 栈并写入日志。
- 每次卡死只 dump 一次，恢复后重新武装，避免刷屏。

只做诊断、不干预业务；抓不到栈也不抛异常。
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)


class MainThreadWatchdog:
    def __init__(self, timeout: float = 3.0, check_interval: float = 1.0):
        """
        :param timeout: 主线程多少秒没心跳判定为卡死。
        :param check_interval: 后台线程检查周期（秒）。
        """
        self._timeout = timeout
        self._check_interval = check_interval
        self._main_thread_id = threading.get_ident()
        self._beat = time.monotonic()
        self._dumped = False  # 当前这次卡死是否已 dump，避免重复
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._qtimer = None  # 持有引用防止被 GC

    def beat(self) -> None:
        """主线程心跳：由 QTimer 在 UI 线程调用。"""
        self._beat = time.monotonic()
        if self._dumped:
            # 从卡死中恢复
            stuck_for = None
            logger.warning("watchdog: 主线程已恢复响应")
            self._dumped = False
            _ = stuck_for

    def start(self, parent=None) -> None:
        """启动看门狗。

        :param parent: 传入 QObject（一般是主窗口）作为 QTimer 的 parent，
                       让心跳 QTimer 跑在主线程事件循环里。
        """
        from PySide6.QtCore import QTimer

        # 主线程心跳定时器：间隔取 check_interval 的一半，保证正常时心跳足够密。
        interval_ms = max(200, int(self._check_interval * 500))
        self._qtimer = QTimer(parent)
        self._qtimer.setInterval(interval_ms)
        self._qtimer.timeout.connect(self.beat)
        self._qtimer.start()

        self._thread = threading.Thread(
            target=self._run, name="MainThreadWatchdog", daemon=True
        )
        self._thread.start()
        logger.info(
            "watchdog: 已启动 timeout=%.1fs check_interval=%.1fs main_tid=%s",
            self._timeout, self._check_interval, self._main_thread_id,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._qtimer is not None:
            self._qtimer.stop()

    def _run(self) -> None:
        while not self._stop.wait(self._check_interval):
            elapsed = time.monotonic() - self._beat
            if elapsed >= self._timeout and not self._dumped:
                self._dump_main_stack(elapsed)
                self._dumped = True

    def _dump_main_stack(self, elapsed: float) -> None:
        try:
            frames = sys._current_frames()
            frame = frames.get(self._main_thread_id)
            if frame is None:
                logger.error(
                    "watchdog: 主线程疑似卡死 %.1fs，但抓不到栈 (tid=%s)",
                    elapsed, self._main_thread_id,
                )
                return
            stack = "".join(traceback.format_stack(frame))
            logger.error(
                "watchdog: 主线程卡死 >= %.1fs，UI 无响应。主线程当前调用栈:\n%s",
                elapsed, stack,
            )
        except Exception:
            logger.exception("watchdog: dump 主线程栈时自身异常")
