# SQLite 数据存储重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 path_history.json / shell_presets.json / config.json 的同步主线程 I/O 替换为 DataStore（内存缓存）+ DataWorker（QThread + SQLite）异步架构，消除 UI 卡死。

**Architecture:** 三部分：DataStore 在主线程提供线程安全的内存读写（微秒级）；DataWorker(QThread) 定时 3s 检查 dirty flag 并选择性 flush 到 SQLite；现有 PathHistory / shell_presets / AppConfig 改为委托给 DataStore。

**Tech Stack:** Python 3.8+, sqlite3（内置）, PySide6, threading.Lock, QThread, pytest

**Spec:** `docs/superpowers/specs/2026-07-13-sqlite-data-store-design.md`

## Global Constraints

- 所有新增/修改代码必须在 `store/` 层无 Qt 依赖（DataWorker 除外）
- 测试沿用现有 pytest 框架，不引入新依赖
- 改动到的文件中可顺手补类型注解，但不得改变行为
- 修改完成后不自动 git commit，需用户验收后主动提示
- `store/paths.py` 现有 `path_history_path()` / `shell_presets_path()` 保留不动（migrate_from_json 和回滚兼容使用）

---

### Task 1: `store/paths.py` — 新增 `database_path()` 和 `config_json_path()`

**Files:**
- Modify: `store/paths.py`

**Interfaces:**
- Produces: `database_path() -> Path`, `config_json_path() -> Path`

- [ ] **Step 1: 在 `store/paths.py` 末尾新增两个函数**

```python
def database_path() -> Path:
    """myterm.db 全路径。打包模式：%LOCALAPPDATA%/MyTerm/myterm.db，开发模式：工程根下 myterm.db。"""
    return local_data_dir() / "myterm.db"


def config_json_path() -> Path:
    """config.json 全路径（与 AppConfig 当前使用路径一致，供迁移阶段读取）。"""
    return local_data_dir() / "config.json"
```

- [ ] **Step 2: 运行 paths 测试验证未破坏现有行为**

```
pytest tests/test_paths.py -v
```

预期: 所有现有测试 PASS

- [ ] **Step 3: 验证新函数可用**

```bash
python -c "from store.paths import database_path, config_json_path; print(database_path()); print(config_json_path())"
```

预期: 输出合法路径，无异常

---

### Task 2: `store/data_store.py` — DataStore 线程安全内存缓存

**Files:**
- Create: `store/data_store.py`
- Create: `tests/test_data_store.py`

**Interfaces:**
- Produces: `DataStore` 类（完整接口见代码）

- [ ] **Step 1: 编写 DataStore 测试文件**

创建 `tests/test_data_store.py`：

```python
"""DataStore 线程安全内存缓存测试。"""
import threading
import time

from store.data_store import DataStore


def test_add_path_appends_and_deduplicates():
    store = DataStore()
    store.add_path("C:\\a")
    store.add_path("C:\\b")
    store.add_path("C:\\a")          # 去重：移到头部
    assert store.get_paths() == ["C:\\a", "C:\\b"]


def test_add_path_truncates_to_10():
    store = DataStore()
    for i in range(15):
        store.add_path(f"C:\\path{i}")
    assert len(store.get_paths()) == 10
    assert store.get_paths()[0] == "C:\\path14"


def test_empty_store_returns_empty_lists():
    store = DataStore()
    assert store.get_paths() == []
    assert store.get_shell_presets_data() == {}
    assert store.get_config_value("any") is None
    assert store.get_config_all() == {}


def test_getters_return_copies():
    """getter 返回副本，外部修改不污染内部状态。"""
    store = DataStore()
    store.add_path("C:\\a")
    paths = store.get_paths()
    paths.append("C:\\evil")
    assert store.get_paths() == ["C:\\a"]

    store.set_shell_presets_data({"version": 2, "presets": [{"label": "x"}]})
    data = store.get_shell_presets_data()
    data["hacked"] = True
    assert store.get_shell_presets_data() == {"version": 2, "presets": [{"label": "x"}]}

    store.set_config_value("k", "v")
    all_cfg = store.get_config_all()
    all_cfg["new"] = "bad"
    assert store.get_config_value("new") is None


def test_dirty_flags_independent():
    """三个 dirty flag 互相独立：只改路径不影响 shell_presets/config 的 dirty 状态。"""
    store = DataStore()
    store.add_path("C:\\a")
    assert store.is_any_dirty() is True

    store.take_snapshot_for_flush()
    assert store.is_any_dirty() is False

    store.set_config_value("layout_mode", "quad")
    assert store.is_any_dirty() is True


def test_take_snapshot_returns_only_dirty():
    store = DataStore()
    store.add_path("C:\\a")                    # 只有 paths dirty
    paths, presets, config = store.take_snapshot_for_flush()
    assert paths == ["C:\\a"]
    assert presets is None
    assert config is None
    assert store.is_any_dirty() is False       # 快照后清除 dirty


def test_take_snapshot_multiple_dirty():
    store = DataStore()
    store.add_path("C:\\a")
    store.set_shell_presets_data({"version": 2, "presets": []})
    store.set_config_value("k", "v")
    paths, presets, config = store.take_snapshot_for_flush()
    assert paths is not None
    assert presets is not None
    assert config is not None


def test_rollback_restores_only_originally_dirty():
    """rollback 只恢复原本 dirty 的 flag，不复全量恢复。"""
    store = DataStore()
    store.add_path("C:\\a")                    # dirty_paths=True, presets=False, config=False
    paths, presets, config = store.take_snapshot_for_flush()
    assert paths is not None
    assert presets is None
    assert config is None

    store.rollback_snapshot()
    # rollback 后 is_any_dirty 应为 True（因为 paths 原本是 dirty）
    assert store.is_any_dirty() is True
    # 再取快照应只返回 paths
    paths2, presets2, config2 = store.take_snapshot_for_flush()
    assert paths2 is not None
    assert presets2 is None
    assert config2 is None


def test_load_initial_data_does_not_mark_dirty():
    store = DataStore()
    assert store.is_any_dirty() is False
    store.load_initial_data(
        paths=["C:\\a", "C:\\b"],
        presets={"version": 2, "presets": [{"label": "x"}]},
        config={"layout_mode": "auto"},
    )
    assert store.is_any_dirty() is False  # 不标记 dirty
    assert store.get_paths() == ["C:\\a", "C:\\b"]
    assert store.get_shell_presets_data() == {"version": 2, "presets": [{"label": "x"}]}
    assert store.get_config_value("layout_mode") == "auto"


def test_concurrent_add_and_take_snapshot():
    """多线程并发 add_path 不应崩溃或丢失数据。"""
    store = DataStore()
    errors = []

    def worker():
        try:
            for i in range(50):
                store.add_path(f"C:\\threaded{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # 快照应包含至少一条路径
    paths, _, _ = store.take_snapshot_for_flush()
    assert paths is not None
    assert len(paths) >= 1


def test_set_paths_replaces_all():
    store = DataStore()
    store.add_path("C:\\old")
    store.set_paths(["C:\\new1", "C:\\new2"])
    assert store.get_paths() == ["C:\\new1", "C:\\new2"]


def test_set_config_value_string_coercion():
    """config value 一律以字符串存储。"""
    store = DataStore()
    store.set_config_value("max_terminals", "4")
    assert store.get_config_value("max_terminals") == "4"
```

- [ ] **Step 2: 运行测试验证失败**

```
pytest tests/test_data_store.py -v
```

预期: 全部 FAIL（DataStore 尚未创建）

- [ ] **Step 3: 创建 `store/data_store.py` 并实现 DataStore**

```python
"""线程安全的内存数据缓存。

主线程读写，DataWorker 线程通过 take_snapshot_for_flush 获取快照并 flush 到 SQLite。
所有公开方法内部用 threading.Lock 保护。
"""
from __future__ import annotations

import threading


class DataStore:
    """线程安全的内存数据缓存。"""

    def __init__(self) -> None:
        self._path_history: list[str] = []
        self._shell_presets_data: dict = {}
        self._config_data: dict[str, str] = {}
        self._dirty_paths = False
        self._dirty_presets = False
        self._dirty_config = False
        self._lock = threading.Lock()
        # snapshot 状态记录（供 rollback_snapshot 精确恢复）
        self._snapshot_was_dirty: tuple[bool, bool, bool] = (False, False, False)

    # ── Path History ──────────────────────────────────────

    def add_path(self, path: str) -> None:
        """添加路径：去重 + 插头部 + 截断至 10 条。"""
        with self._lock:
            if path in self._path_history:
                self._path_history.remove(path)
            self._path_history.insert(0, path)
            del self._path_history[10:]
            self._dirty_paths = True

    def get_paths(self) -> list[str]:
        """返回路径历史副本。"""
        with self._lock:
            return list(self._path_history)

    def set_paths(self, paths: list[str]) -> None:
        """整量替换（迁移用）。"""
        with self._lock:
            self._path_history = list(paths)
            self._dirty_paths = True

    # ── Shell Presets ─────────────────────────────────────

    def get_shell_presets_data(self) -> dict:
        """返回 shell_presets 数据的浅拷贝。"""
        with self._lock:
            return dict(self._shell_presets_data)

    def set_shell_presets_data(self, data: dict) -> None:
        """整量替换 shell_presets 数据。"""
        with self._lock:
            self._shell_presets_data = dict(data)
            self._dirty_presets = True

    # ── Config ────────────────────────────────────────────

    def get_config_value(self, key: str, default: str | None = None) -> str | None:
        """读取单个配置项。"""
        with self._lock:
            return self._config_data.get(key, default)

    def set_config_value(self, key: str, value: str) -> None:
        """设置单个配置项。"""
        with self._lock:
            self._config_data[key] = value
            self._dirty_config = True

    def get_config_all(self) -> dict[str, str]:
        """返回全部配置副本。"""
        with self._lock:
            return dict(self._config_data)

    # ── Worker 线程接口 ───────────────────────────────────

    def is_any_dirty(self) -> bool:
        """持锁读取三个 dirty flag。"""
        with self._lock:
            return self._dirty_paths or self._dirty_presets or self._dirty_config

    def load_initial_data(
        self, paths: list[str], presets: dict, config: dict[str, str]
    ) -> None:
        """仅用于 DataWorker Phase 1 加载，不标记 dirty。"""
        with self._lock:
            self._path_history = list(paths)
            self._shell_presets_data = dict(presets)
            self._config_data = dict(config)

    def take_snapshot_for_flush(self) -> tuple[list | None, dict | None, dict | None]:
        """原子操作：复制脏数据 + 清除 dirty flag + 记录 snapshot 状态。"""
        with self._lock:
            paths = (
                list(self._path_history) if self._dirty_paths else None
            )
            presets = (
                dict(self._shell_presets_data) if self._dirty_presets else None
            )
            config = (
                dict(self._config_data) if self._dirty_config else None
            )
            self._snapshot_was_dirty = (
                self._dirty_paths,
                self._dirty_presets,
                self._dirty_config,
            )
            self._dirty_paths = False
            self._dirty_presets = False
            self._dirty_config = False
        return (paths, presets, config)

    def rollback_snapshot(self) -> None:
        """flush 失败时恢复原本 dirty 的 flag（不恢复全量）。"""
        with self._lock:
            dp, dpr, dc = self._snapshot_was_dirty
            if dp:
                self._dirty_paths = True
            if dpr:
                self._dirty_presets = True
            if dc:
                self._dirty_config = True
```

- [ ] **Step 4: 运行测试验证通过**

```
pytest tests/test_data_store.py -v
```

预期: 全部 PASS

---

### Task 3: `store/data_worker.py` — DataWorker(QThread) + SQLite 持久化

**Files:**
- Create: `store/data_worker.py`
- Create: `tests/test_data_worker.py`

**Interfaces:**
- Consumes: `DataStore` 类（Task 2）
- Produces: `DataWorker(QThread)` 类，包含信号 `data_loaded` / `data_flushed`

- [ ] **Step 1: 编写 DataWorker 测试文件**

创建 `tests/test_data_worker.py`：

```python
"""DataWorker 测试：建表、flush、退出 flush、空数据库启动。"""
import json
import time
from pathlib import Path

import pytest

from store.data_store import DataStore
from store.data_worker import DataWorker


@pytest.fixture
def store():
    return DataStore()


def test_data_worker_creates_tables(store, tmp_path):
    """首次启动时创建三张表，无 JSON 迁移，data_loaded 正常触发。"""
    db = tmp_path / "test.db"
    worker = DataWorker(store, db)
    worker.start()
    worker.wait(5000)

    # data_loaded 应已触发
    assert store.is_any_dirty() is False  # load_initial_data 不标记 dirty

    # 验证数据库文件存在且有内容
    import sqlite3
    conn = sqlite3.connect(str(db))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {r[0] for r in tables}
    assert table_names >= {"path_history", "shell_presets", "config"}
    conn.close()

    assert not worker.isRunning()


def test_flush_persists_path_history(store, tmp_path):
    """添加路径，等待 flush，重启 worker 后数据应恢复。"""
    db = tmp_path / "test.db"
    # 首次运行：添加数据并退出
    worker1 = DataWorker(store, db)
    worker1.start()
    worker1.wait(5000)

    store.add_path("C:\\test")
    time.sleep(0.5)  # 等一次 flush 周期（3s 太长，直接调 _flush_if_dirty）

    # 手动触发一次 flush 并等待
    import sqlite3
    conn = sqlite3.connect(str(db))
    worker1._conn = conn
    worker1._flush_if_dirty()
    conn.close()

    worker1.requestInterruption()
    worker1.wait(5000)

    # 第二次启动：数据应已恢复
    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.wait(5000)
    assert store2.get_paths() == ["C:\\test"]


def test_flush_persists_config(store, tmp_path):
    """配置写入后重启可恢复。"""
    db = tmp_path / "test.db"
    worker1 = DataWorker(store, db)
    worker1.start()
    worker1.wait(5000)

    store.set_config_value("layout_mode", "quad")
    store.set_config_value("max_terminals", "6")

    import sqlite3
    conn = sqlite3.connect(str(db))
    worker1._conn = conn
    worker1._flush_if_dirty()
    conn.close()
    worker1.requestInterruption()
    worker1.wait(5000)

    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.wait(5000)
    assert store2.get_config_value("layout_mode") == "quad"
    assert store2.get_config_value("max_terminals") == "6"


def test_clean_exit_flushes_dirty_data(store, tmp_path):
    """退出时 Phase 3 强制 flush 脏数据。"""
    db = tmp_path / "test.db"
    worker1 = DataWorker(store, db)
    worker1.start()
    worker1.wait(5000)

    store.add_path("C:\\last_data")
    worker1.requestInterruption()
    worker1.wait(5000)

    assert not worker1.isRunning()

    # 重启恢复
    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.wait(5000)
    assert "C:\\last_data" in store2.get_paths()


def test_empty_database_starts_clean(store, tmp_path):
    """无 JSON 文件、无旧数据库时静默启动。"""
    db = tmp_path / "fresh.db"
    worker = DataWorker(store, db)
    worker.start()
    worker.wait(5000)

    assert store.get_paths() == []
    assert store.get_shell_presets_data() == {}
    assert store.get_config_all() == {}


def test_flush_rolls_back_on_oserror(store, tmp_path):
    """flush 失败时 rollback_snapshot 恢复 dirty flag。"""
    db = tmp_path / "test.db"
    worker = DataWorker(store, db)
    worker.start()
    worker.wait(5000)

    store.add_path("C:\\important")
    assert store.is_any_dirty() is True

    # 模拟写入失败
    conn = sqlite3.connect(str(db))
    worker._conn = conn
    from unittest.mock import patch
    with patch.object(conn, "commit", side_effect=sqlite3.Error("模拟失败")):
        worker._flush_if_dirty()

    conn.close()
    # dirty flag 已被 rollback 恢复
    assert store.is_any_dirty() is True

    worker.requestInterruption()
    worker.wait(5000)
```

- [ ] **Step 2: 运行测试验证失败**

```
pytest tests/test_data_worker.py -v
```

预期: 全部 FAIL（DataWorker 尚未创建）

- [ ] **Step 3: 创建 `store/data_worker.py` 并实现 DataWorker**

```python
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
            path_history_path,
            shell_presets_path,
            config_json_path,
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
```

- [ ] **Step 4: 运行测试验证通过**

```
pytest tests/test_data_worker.py -v
```

预期: 全部 PASS

---

### Task 4: `tests/test_migration.py` — JSON → SQLite 迁移测试

**Files:**
- Create: `tests/test_migration.py`

**Interfaces:**
- Consumes: `DataStore`, `DataWorker`（Task 2, 3）

- [ ] **Step 1: 编写迁移测试**

```python
"""JSON → SQLite 迁移测试：幂等性、部分迁移、损坏 JSON 降级。"""
import json
import sqlite3
from pathlib import Path

from store.data_store import DataStore
from store.data_worker import DataWorker


def test_migration_from_json_files(monkeypatch, tmp_path):
    """三个 JSON 文件都存在，首次启动时全部迁移到 SQLite。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)

    # 准备 JSON 文件
    (tmp_path / "path_history.json").write_text(
        json.dumps(["C:\\a", "C:\\b"]), encoding="utf-8")
    (tmp_path / "shell_presets.json").write_text(json.dumps({
        "version": 2,
        "presets": [{"label": "claude", "host": "cmd", "command": "claude"}],
    }), encoding="utf-8")
    (tmp_path / "config.json").write_text(
        json.dumps({"layout_mode": "quad", "max_terminals": 6}), encoding="utf-8")

    store = DataStore()
    db = tmp_path / "myterm.db"
    worker = DataWorker(store, db)
    worker.start()
    worker.wait(5000)

    assert store.get_paths() == ["C:\\a", "C:\\b"]
    data = store.get_shell_presets_data()
    assert data.get("presets")
    assert store.get_config_value("layout_mode") == "quad"
    assert store.get_config_value("max_terminals") == "6"


def test_migration_idempotent(monkeypatch, tmp_path):
    """第二次启动时不重复迁移（表已有数据，跳过）。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)

    (tmp_path / "path_history.json").write_text(
        json.dumps(["C:\\original"]), encoding="utf-8")

    # 第一次迁移
    store1 = DataStore()
    w1 = DataWorker(store1, tmp_path / "myterm.db")
    w1.start()
    w1.wait(5000)
    assert store1.get_paths() == ["C:\\original"]

    # 修改 JSON 文件（模拟降级后手动编辑）
    (tmp_path / "path_history.json").write_text(
        json.dumps(["C:\\changed"]), encoding="utf-8")

    # 第二次启动：SQLite 已有数据，跳过迁移，不会读到 changed
    store2 = DataStore()
    w2 = DataWorker(store2, tmp_path / "myterm.db")
    w2.start()
    w2.wait(5000)
    assert store2.get_paths() == ["C:\\original"]  # 不是 changed


def test_corrupt_json_skipped(monkeypatch, tmp_path):
    """损坏的 JSON 文件跳过迁移，不阻塞启动。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)

    (tmp_path / "path_history.json").write_bytes(b"{not valid")
    # 还有一个正常的 config
    (tmp_path / "config.json").write_text(
        json.dumps({"layout_mode": "v"}), encoding="utf-8")

    store = DataStore()
    worker = DataWorker(store, tmp_path / "myterm.db")
    worker.start()
    worker.wait(5000)

    # path_history 迁移失败，SQLite 为空
    assert store.get_paths() == []
    # config 迁移成功
    assert store.get_config_value("layout_mode") == "v"


def test_no_json_files_starts_clean(monkeypatch, tmp_path):
    """无 JSON 文件时静默启动，不创建 JSON 文件。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)

    store = DataStore()
    worker = DataWorker(store, tmp_path / "myterm.db")
    worker.start()
    worker.wait(5000)

    assert store.get_paths() == []
    assert not (tmp_path / "path_history.json").exists()  # 不创建 JSON
```

- [ ] **Step 2: 运行测试**

```
pytest tests/test_migration.py -v
```

预期: 全部 PASS

---

### Task 5: `store/path_history.py` — 委托给 DataStore

**Files:**
- Modify: `store/path_history.py`
- Modify: `tests/test_path_history.py`

**Interfaces:**
- Consumes: `DataStore`（Task 2）
- Produces: `PathHistory` 类（`__init__(self, store: DataStore)` 替代 `filepath`）

- [ ] **Step 1: 改写 `store/path_history.py`**

```python
"""路径历史：内存操作委托给 DataStore，不再直接读写文件。"""
from __future__ import annotations

from store.data_store import DataStore


class PathHistory:
    """路径历史管理器。add/all 委托给 DataStore 内存缓存。"""

    def __init__(self, store: DataStore) -> None:
        self._store = store

    def add(self, path: str) -> None:
        """添加路径到历史（去重 + 插头部 + 截断 10 条）。纯内存操作。"""
        self._store.add_path(path)

    def all(self) -> list[str]:
        """返回当前路径历史副本。"""
        return self._store.get_paths()
```

- [ ] **Step 2: 更新 `tests/test_path_history.py`**

将 `PathHistory(filepath=str(tmp_path / "test.json"))` 全部替换为注入 DataStore 的模式：

```python
from store.data_store import DataStore
from store.path_history import PathHistory


def test_add_and_get_recent():
    store = DataStore()
    history = PathHistory(store)
    history.add("C:\\Users")
    history.add("C:\\Windows")
    assert history.all() == ["C:\\Windows", "C:\\Users"]


def test_dedup_moves_to_top():
    store = DataStore()
    history = PathHistory(store)
    history.add("C:\\Users")
    history.add("C:\\Windows")
    history.add("C:\\Users")
    assert history.all() == ["C:\\Users", "C:\\Windows"]


def test_max_ten_entries():
    store = DataStore()
    history = PathHistory(store)
    for i in range(15):
        history.add(f"C:\\path{i}")
    paths = history.all()
    assert len(paths) == 10
    assert paths[0] == "C:\\path14"


def test_empty_history_returns_empty_list():
    store = DataStore()
    history = PathHistory(store)
    assert history.all() == []


def test_persist_through_data_store():
    """两个 PathHistory 共享同一个 DataStore，数据保持。"""
    store = DataStore()
    history_a = PathHistory(store)
    history_a.add("C:\\test")
    history_b = PathHistory(store)
    assert history_b.all() == ["C:\\test"]
```

注意：旧的 `test_save_writes_directly_no_tmp`、`test_save_swallows_oserror`、`test_load_survives_truncated_file` 删除，因为 PathHistory 不再直接读写文件。

- [ ] **Step 3: 运行 path_history 测试**

```
pytest tests/test_path_history.py -v
```

预期: 全部 PASS

---

### Task 6: `store/shell_presets.py` — load/save 改为 DataStore 后端

**Files:**
- Modify: `store/shell_presets.py`
- Modify: `tests/test_shell_presets.py`

**Interfaces:**
- Consumes: `DataStore`（Task 2）
- Produces: `load(store: DataStore) -> list[ShellPreset]`, `save(presets, store)`

- [ ] **Step 1: 改写 `load()` 和 `save()` 函数**

在 `store/shell_presets.py` 中修改：

```python
def load(store: DataStore) -> list[ShellPreset]:
    """从 DataStore 内存缓存读取预设列表。

    数据为空时回退到内置默认预设（如 powershell / cmd），写入 DataStore
    （纯内存操作），由 DataWorker 定时 flush 到 SQLite。
    """
    from store.data_store import DataStore  # type guard

    data = store.get_shell_presets_data()
    preset_dicts = data.get("presets", [])
    if not preset_dicts:
        defaults = default_presets()
        save(defaults, store)
        return list(defaults)
    return [_parse_one(item, i) for i, item in enumerate(preset_dicts)]


def save(presets: list[ShellPreset], store: DataStore) -> None:
    """将预设列表序列化后写入 DataStore 内存缓存。"""
    payload: dict = {
        "version": SCHEMA_VERSION,
        "presets": [_serialize_one(p) for p in presets],
    }
    store.set_shell_presets_data(payload)
```

注意：
- 保留旧的 `load(path=None)` 签名中的 `path` 参数做兼容（设为可选参数，默认为 None 时用 DataStore）
- 实际上直接改签名更干净，因为所有现有调用方将在后续 task 中更新
- `save()` 同样改签名，移除 `path=` 参数

- [ ] **Step 2: 更新 `tests/test_shell_presets.py`**

对于使用 `load(path=target)` 和 `save(presets, path=target)` 的测试，改为注入 DataStore：

```python
from store.data_store import DataStore
from store.shell_presets import load, save, default_presets, ShellPreset


def test_load_returns_default_when_empty():
    store = DataStore()
    presets = load(store)
    assert [p.label for p in presets] == ["powershell", "cmd"]
    # 默认预设已写入 DataStore 内存
    data = store.get_shell_presets_data()
    assert data["presets"]


def test_load_from_store():
    store = DataStore()
    store.set_shell_presets_data({
        "version": 2,
        "presets": [{"label": "claude", "host": "cmd", "command": "claude"}],
    })
    presets = load(store)
    assert presets[0].label == "claude"


def test_save_load_roundtrip():
    store = DataStore()
    original = [
        ShellPreset(label="powershell", host="none", raw_command="powershell.exe"),
        ShellPreset(label="claude", host="powershell", raw_command="claude"),
    ]
    save(original, store)
    loaded = load(store)
    assert len(loaded) == 2
    for a, b in zip(original, loaded):
        assert a.label == b.label
        assert a.host == b.host
        assert a.raw_command == b.raw_command
```

注意：原有测试中大量使用 `load(path=target)` + 写入 JSON 文件的测试（如 `test_load_returns_default_when_corrupt`、`test_load_skips_invalid_entry` 等），这些测试验证的是旧 JSON 文件解析逻辑。重构后 JSON 解析逻辑移到 `_migrate_from_json()` 中，这些测试应移到 `tests/test_migration.py`。本文件只保留 DataStore 后端的测试。

- [ ] **Step 3: 运行 shell_presets 测试**

```
pytest tests/test_shell_presets.py -v
```

预期: 保留的测试 PASS，移走的测试后续在 migration 测试中覆盖

---

### Task 7: `store/config.py` — AppConfig 改为 DataStore 后端

**Files:**
- Modify: `store/config.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `DataStore`（Task 2）, `shell_presets.load(store)`（Task 6）
- Produces: `AppConfig(store: DataStore)` 类

- [ ] **Step 1: 改写 `store/config.py` 的 `AppConfig` 类**

```python
class AppConfig:
    """应用配置入口。从 DataStore 读取，通过 DataWorker 持久化到 SQLite。"""

    def __init__(self, store: DataStore) -> None:
        from store.data_store import DataStore
        self._store: DataStore = store

        mode_str = store.get_config_value("layout_mode", "auto")
        self.layout_mode: LayoutMode = LayoutMode(mode_str)

        max_str = store.get_config_value("max_terminals", "4")
        self._max_terminals: int = min(max(int(max_str), 1), _HARD_MAX_TERMINALS)

        from store import shell_presets
        self._shell_presets: list = shell_presets.load(store)

        logger.info("配置加载完成: max_terminals=%d, layout_mode=%s, presets=%d",
                     self._max_terminals, self.layout_mode.value, len(self._shell_presets))

    def save(self) -> None:
        """将可写配置写入 DataStore 内存（纯内存操作，DataWorker 定时 flush）。"""
        self._store.set_config_value("layout_mode", self.layout_mode.value)
        self._store.set_config_value("max_terminals", str(self._max_terminals))

    def reload_shell_presets(self) -> None:
        """重新加载预设数据。"""
        from store import shell_presets
        self._shell_presets = shell_presets.load(self._store)
        logger.info("预设重载完成, 共 %d 条", len(self._shell_presets))

    @property
    def shell_presets(self):
        return list(self._shell_presets)

    @property
    def max_terminals(self) -> int:
        return self._max_terminals
```

删除：
- `_CONFIG_FILE`、`_load_json()`、`self._config_path`、`self._shell_presets_module`

- [ ] **Step 2: 更新 `tests/test_config.py`**

```python
from store.data_store import DataStore
from store.config import AppConfig, compute_grid_shape, compute_grid_shape_for, LayoutMode


def test_app_config_reads_layout_mode_from_store():
    store = DataStore()
    store.set_config_value("layout_mode", "quad")
    cfg = AppConfig(store)
    assert cfg.layout_mode == LayoutMode.QUAD


def test_app_config_defaults_when_store_empty():
    store = DataStore()
    cfg = AppConfig(store)
    assert cfg.layout_mode == LayoutMode.AUTO


def test_app_config_save_writes_to_store():
    store = DataStore()
    cfg = AppConfig(store)
    cfg.layout_mode = LayoutMode.HORIZONTAL
    cfg.save()
    assert store.get_config_value("layout_mode") == "h"
    assert store.get_config_value("max_terminals") == "4"


def test_app_config_save_writes_both_keys():
    store = DataStore()
    store.set_config_value("max_terminals", "6")
    cfg = AppConfig(store)
    cfg.layout_mode = LayoutMode.VERTICAL
    cfg.save()
    assert store.get_config_value("layout_mode") == "v"
    assert store.get_config_value("max_terminals") == "6"


def test_app_config_reload_shell_presets():
    store = DataStore()
    # 模拟迁移后或用户保存后的数据
    store.set_shell_presets_data({
        "version": 2,
        "presets": [{"label": "claude", "host": "cmd", "command": "claude"}],
    })
    cfg = AppConfig(store)
    labels = [p.label for p in cfg.shell_presets]
    assert labels == ["claude"]

    # 修改后重新加载
    store.set_shell_presets_data({
        "version": 2,
        "presets": [{"label": "new-one", "host": "none", "command": "x.exe"}],
    })
    cfg.reload_shell_presets()
    assert [p.label for p in cfg.shell_presets] == ["new-one"]


# compute_grid_shape 等纯逻辑函数测试不变，保留
def test_compute_grid_shape(n, expected): ...
def test_compute_grid_shape_for_auto(): ...
def test_compute_grid_shape_for_quad(): ...
def test_compute_grid_shape_for_horizontal(): ...
def test_compute_grid_shape_for_vertical(): ...
```

注意：移除旧测试中依赖 `isinstance(数据, AppConfig)` 检查 `_load_json` 的内容，以及 `monkeypatch` 对 `store.paths` 的路径修改，因为 AppConfig 不再直接读文件。

- [ ] **Step 3: 运行 config 测试**

```
pytest tests/test_config.py -v
```

预期: 全部 PASS

---

### Task 8: `main.py` — 创建 DataStore + DataWorker，管理生命周期

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `DataStore`, `DataWorker`, `MainWindow`（Task 2, 3, 9）
- Produces: 完整的应用启动序列

- [ ] **Step 1: 改写 `main.py`**

```python
"""MyTerm — 多终端启动器入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from store.data_store import DataStore
from store.data_worker import DataWorker
from store.paths import database_path, migrate_legacy_files
from store.log import setup_logging
from store.watchdog import MainThreadWatchdog
from ui.main_window import MainWindow


def main() -> None:
    migrate_legacy_files()
    setup_logging()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    store = DataStore()
    worker = DataWorker(store, database_path())
    window = MainWindow(store)
    worker.data_loaded.connect(window.on_data_loaded)
    worker.start()

    window.show()

    def on_about_to_quit() -> None:
        worker.requestInterruption()
        worker.wait(5000)

    app.aboutToQuit.connect(on_about_to_quit)

    watchdog = MainThreadWatchdog(timeout=3.0, check_interval=1.0)
    watchdog.start(parent=window)

    rc = app.exec()
    sys.exit(rc)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证语法和导入**

```
python -c "import main; print('import OK')"
```

预期: 输出 `import OK`，无 ImportError

---

### Task 9: `ui/main_window.py` — 接受 DataStore，连接 data_loaded

**Files:**
- Modify: `ui/main_window.py`

**Interfaces:**
- Consumes: `DataStore`, `PathHistory`, `AppConfig`（Task 2, 5, 7）
- Produces: `MainWindow(store: DataStore)` 构造函数 + `on_data_loaded()` + `_rebuild_shell_combo()`

- [ ] **Step 1: 修改 `MainWindow.__init__` 接受 DataStore**

将原来的：

```python
from store.path_history import PathHistory
from store.config import AppConfig
```

改为从构造参数获取 `store`，通过它创建 `PathHistory` 和 `AppConfig`：

```python
def __init__(self, store: DataStore) -> None:
    from store.data_store import DataStore  # type guard
    from store.path_history import PathHistory
    from store.config import AppConfig

    super().__init__()
    self._store: DataStore = store
    self._history: PathHistory = PathHistory(store)
    self._config: AppConfig = AppConfig(store)
    self._slots: list = []
    # ... 其余 __init__ 逻辑不变
    self._setup_ui()
```

- [ ] **Step 2: 从 `__init__` 中抽取 `_rebuild_shell_combo()`**

当前 `__init__` 中有填充 `_shell_combo` 的循环。抽取为独立方法：

```python
def _rebuild_shell_combo(self) -> None:
    """重建 shell 下拉框。清空后重新填入预设；保留当前选中项。"""
    old_label = self._shell_combo.currentText() if self._shell_combo.count() > 0 else ""
    self._shell_combo.blockSignals(True)
    self._shell_combo.clear()
    for preset in self._config.shell_presets:
        self._shell_combo.addItem(preset.label, preset)
    if old_label:
        idx = self._shell_combo.findText(old_label)
        if idx >= 0:
            self._shell_combo.setCurrentIndex(idx)
    self._shell_combo.blockSignals(False)
```

在 `__init__` 中调用 `self._rebuild_shell_combo()` 代替原来的循环。

- [ ] **Step 3: 新增 `on_data_loaded()` 方法**

```python
def on_data_loaded(self) -> None:
    """DataWorker 数据加载完毕后刷新 UI。"""
    self._load_history()
    self._config.reload_shell_presets()
    self._rebuild_shell_combo()
```

- [ ] **Step 4: 修改 `_load_history()` 防止重复追加**

在原 `_load_history()` 方法开头增加 `self._path_combo.clear()`：

```python
def _load_history(self) -> None:
    self._path_combo.clear()  # 新增：防止重复追加
    paths = self._history.all()
    for p in paths:
        self._path_combo.addItem(p)
```

- [ ] **Step 5: 修改 `_on_presets_changed` 增加 save 调用**

```python
def _on_presets_changed(self, new_presets=None) -> None:
    if new_presets is not None:
        from store import shell_presets
        shell_presets.save(new_presets, self._store)  # 新增：写入 DataStore
    self._config.reload_shell_presets()
    self._rebuild_shell_combo()  # 替换原来的手动循环
```

删除原来 `_on_presets_changed` 中的手动 `_shell_combo.clear()` + `addItem()` 循环，改用 `_rebuild_shell_combo()`。

---

### Task 10: UI 对话框更新

**Files:**
- Modify: `ui/shell_presets_dialog.py`
- Modify: `ui/cli_install_dialog.py`

**Interfaces:**
- Consumes: `DataStore`（Task 2）, `shell_presets.save/store`（Task 6）

- [ ] **Step 1: `shell_presets_dialog.py` — 移除内部 `shell_presets.save` 调用**

找到 `ShellPresetsDialog` 中保存按钮的处理代码（约第308行）：

```python
# 原代码：
shell_presets.save(presets)
self.presets_changed.emit(presets)
```

改为：

```python
# 仅 emit 信号，save 由 MainWindow._on_presets_changed() 处理
self.presets_changed.emit(presets)
```

- [ ] **Step 2: `cli_install_dialog.py` — 构造器增加 store 参数**

在 `CliInstallDialog.__init__` 增加 `store` 参数：

```python
def __init__(self, store: DataStore, parent=None) -> None:
    super().__init__(parent)
    self._store = store
```

将内部的 `load_presets()` 和 `save_presets(new_list)` 调用改为：

```python
# 原代码：
current = load_presets()
# 改为：
current = load_presets(self._store)

# 原代码：
save_presets(new_list)
# 改为：
save_presets(new_list, self._store)
```

在 `ui/main_window.py` 中创建 `CliInstallDialog` 时传入 `self._store`。

- [ ] **Step 3: 运行对话框相关测试**

```
pytest tests/test_shell_presets_dialog.py tests/test_cli_install_dialog.py -v
```

预期: 全部 PASS（或针对 Qt 依赖的 skip 正常）

---

### Task 11: 全量测试 + 手动验证

**Files:**
- None（验证步骤）

- [ ] **Step 1: 运行全部现有测试**

```
pytest tests/ -v --timeout=30
```

预期: 所有测试 PASS，无新增失败

- [ ] **Step 2: 手动启动验证**

```
python main.py
```

验证：
1. 窗口正常显示，shell 下拉框有 powershell / cmd 预设
2. 浏览并启动终端，路径历史正常记录
3. 关闭窗口后重启，路径历史和布局设置保持
4. 修改布局模式（quad/h/v），关闭重启后设置保持

- [ ] **Step 3: 首次启动验证（无 myterm.db）**

删除 `local_data_dir/myterm.db`（开发模式下即工程根下的 `myterm.db`），启动应用。验证：
1. 首次启动创建 myterm.db
2. 若存在旧 JSON 文件，数据已迁移
3. shell 下拉框有默认预设

---
