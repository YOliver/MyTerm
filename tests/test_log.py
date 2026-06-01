"""日志模块测试。"""
from __future__ import annotations

import logging

import pytest

from store.paths import log_dir
from store.log import setup_logging


def test_log_dir_exists(tmp_path, monkeypatch):
    """log_dir() 应返回已存在的目录。"""
    monkeypatch.setattr("store.paths.project_root", lambda: tmp_path)
    d = log_dir()
    assert d.is_dir()
    assert d == tmp_path / "logs"


def test_setup_logging_writes_file(tmp_path, monkeypatch):
    """setup_logging() 后写一条日志，文件应有内容。"""
    monkeypatch.setattr("store.paths.project_root", lambda: tmp_path)
    # 清除之前可能存在的 handler，避免测试间互相影响
    root = logging.getLogger()
    old_handlers = root.handlers[:]
    root.handlers.clear()
    try:
        setup_logging()
        logging.getLogger("test").info("hello")
        log_file = tmp_path / "logs" / "myterm.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "hello" in content
    finally:
        root.handlers = old_handlers
