"""应用日志初始化。

使用 stdlib logging + TimedRotatingFileHandler，日志文件写入 store.paths.log_dir()。
每天凌晨 0 点切换新文件，保留 30 天。
应在 main() 入口最早阶段调用 setup_logging()。
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from store.paths import log_dir


def setup_logging() -> None:
    """配置根 logger：每天凌晨轮转，保留 30 天。"""
    log_path = log_dir() / "myterm.log"
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
