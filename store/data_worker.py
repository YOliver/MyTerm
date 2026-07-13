"""DataWorker — QThread 后台线程，负责 SQLite 持久化。

Phase 1: 建表 → JSON 迁移 → 加载到 DataStore → emit data_loaded
Phase 2: 定时 3s 检查 dirty → 选择性 flush
Phase 3: 退出时强制 flush + 关闭连接
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from store.data_store import DataStore

logger = logging.getLogger(__name__)


class DataWorker(QThread):
    """SQLite 持久化后台线程。"""

    data_loaded = Signal()      # 初始数据加载完毕
    data_flushed = Signal()     # 每次 flush 完成

    def __init__(self, store: DataStore, db_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._db_path = db_path
        self._flush_interval = 3000  # ms

    def run(self) -> None:
        # Phase 1: 初始化数据库 + 加载数据
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
        try:
            self._migrate_from_json()
        except Exception:
            logger.exception("JSON 迁移失败，从空表继续")
        try:
            self._load_all_to_store()
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.exception("SQLite 数据加载失败: %s", e)
            try:
                self._conn.close()
                self._db_path.unlink(missing_ok=True)
                self._conn = sqlite3.connect(str(self._db_path))
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._create_tables()
                self._migrate_from_json()
                self._load_all_to_store()
            except Exception:
                logger.exception("恢复失败，空表启动")
        self.data_loaded.emit()

        # Phase 2: 定时 flush 循环
        last_flush = time.monotonic()
        while not self.isInterruptionRequested():
            now = time.monotonic()
            if now - last_flush >= self._flush_interval / 1000.0:
                self._flush_if_dirty()
                last_flush = now
            self.msleep(100)

        # Phase 3: 退出时强制 flush
        self._flush_if_dirty()
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS path_history (
                path TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shell_presets (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

    def _migrate_from_json(self) -> None:
        """逐表判断是否需要从旧 JSON 迁移到 SQLite。路径函数来自 store/paths.py。"""
        from store.paths import (
            path_history_path, shell_presets_path, config_json_path,
        )

        self._conn.execute("BEGIN")
        try:
            # path_history
            php = path_history_path()
            if php.exists():
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM path_history"
                ).fetchone()[0]
                if count == 0:
                    try:
                        data = json.loads(php.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            for i, p in enumerate(data):
                                self._conn.execute(
                                    "INSERT INTO path_history (path, sort_order) VALUES (?, ?)",
                                    (p, i),
                                )
                    except (json.JSONDecodeError, OSError):
                        pass

            # shell_presets
            sp = shell_presets_path()
            if sp.exists():
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM shell_presets"
                ).fetchone()[0]
                if count == 0:
                    try:
                        data = json.loads(sp.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and "presets" in data:
                            self._conn.execute(
                                "INSERT INTO shell_presets (id, data) VALUES (1, ?)",
                                (json.dumps(data, ensure_ascii=False),),
                            )
                    except (json.JSONDecodeError, OSError):
                        pass

            # config
            cfp = config_json_path()
            if cfp.exists():
                count = self._conn.execute(
                    "SELECT COUNT(*) FROM config"
                ).fetchone()[0]
                if count == 0:
                    try:
                        data = json.loads(cfp.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            for k, v in data.items():
                                self._conn.execute(
                                    "INSERT INTO config (key, value) VALUES (?, ?)",
                                    (k, str(v)),
                                )
                    except (json.JSONDecodeError, OSError):
                        pass

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _load_all_to_store(self) -> None:
        """从 SQLite 读取全部数据，通过 load_initial_data 写入 DataStore（不标记 dirty）。"""
        paths_rows = self._conn.execute(
            "SELECT path FROM path_history ORDER BY sort_order"
        ).fetchall()
        paths = [row[0] for row in paths_rows]

        presets_row = self._conn.execute(
            "SELECT data FROM shell_presets WHERE id = 1"
        ).fetchone()
        presets_data = json.loads(presets_row[0]) if presets_row else {}

        config_rows = self._conn.execute(
            "SELECT key, value FROM config"
        ).fetchall()
        config_data = {row[0]: row[1] for row in config_rows}

        self._store.load_initial_data(paths, presets_data, config_data)

    def _flush_if_dirty(self) -> None:
        """检查并仅 flush 有变更的数据类型。"""
        if not self._store.is_any_dirty():
            return
        paths, presets, config = self._store.take_snapshot_for_flush()
        try:
            if paths is not None:
                self._conn.execute("DELETE FROM path_history")
                for i, p in enumerate(paths):
                    self._conn.execute(
                        "INSERT INTO path_history (path, sort_order) VALUES (?, ?)",
                        (p, i),
                    )
            if presets is not None:
                self._conn.execute("DELETE FROM shell_presets")
                self._conn.execute(
                    "INSERT INTO shell_presets (id, data) VALUES (1, ?)",
                    (json.dumps(presets, ensure_ascii=False),),
                )
            if config is not None:
                self._conn.execute("DELETE FROM config")
                for k, v in config.items():
                    self._conn.execute(
                        "INSERT INTO config (key, value) VALUES (?, ?)", (k, v),
                    )
            self._conn.commit()
            self.data_flushed.emit()
        except sqlite3.Error:
            logger.exception("flush 失败，下次重试")
            self._store.rollback_snapshot()
