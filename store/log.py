"""应用日志初始化。

使用 stdlib logging + RotatingFileHandler，日志文件写入 store.paths.log_dir()。
应在 main() 入口最早阶段调用 setup_logging()。
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from store.paths import log_dir


def setup_logging() -> None:
    """配置根 logger：5 MB 轮转、保留 3 个备份。"""
    log_path = log_dir() / "myterm.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
