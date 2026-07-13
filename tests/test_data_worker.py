"""DataWorker 测试：建表、flush、退出 flush、空数据库启动。"""
import sqlite3

from store.data_store import DataStore
from store.data_worker import DataWorker


def _monkeypatch_paths(monkeypatch, tmp_path):
    """将 store/paths 的本地数据路径重定向到 tmp_path，防止迁移阶段读取真实 JSON。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)


def test_data_worker_creates_tables(tmp_path, monkeypatch):
    """首次启动时创建三张表，无 JSON 迁移，data_loaded 正常触发。"""
    _monkeypatch_paths(monkeypatch, tmp_path)
    store = DataStore()
    db = tmp_path / "test.db"
    worker = DataWorker(store, db)
    worker.start()
    worker.requestInterruption()
    worker.wait(5000)

    assert not worker.isRunning()
    assert store.is_any_dirty() is False

    conn = sqlite3.connect(str(db))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {r[0] for r in tables}
    assert table_names >= {"path_history", "shell_presets", "config"}
    conn.close()


def test_flush_persists_path_history(tmp_path, monkeypatch):
    """添加路径 → flush → 重启恢复。"""
    _monkeypatch_paths(monkeypatch, tmp_path)
    db = tmp_path / "test.db"
    store = DataStore()
    worker1 = DataWorker(store, db)
    worker1.start()
    worker1.requestInterruption()
    worker1.wait(5000)

    store.add_path("C:\\test")

    conn = sqlite3.connect(str(db))
    worker1._conn = conn
    worker1._flush_if_dirty()
    conn.close()

    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.requestInterruption()
    worker2.wait(5000)
    assert store2.get_paths() == ["C:\\test"]


def test_flush_persists_config(tmp_path, monkeypatch):
    """配置写入后重启可恢复。"""
    _monkeypatch_paths(monkeypatch, tmp_path)
    db = tmp_path / "test.db"
    store = DataStore()
    worker1 = DataWorker(store, db)
    worker1.start()
    worker1.requestInterruption()
    worker1.wait(5000)

    store.set_config_value("layout_mode", "quad")
    store.set_config_value("max_terminals", "6")

    conn = sqlite3.connect(str(db))
    worker1._conn = conn
    worker1._flush_if_dirty()
    conn.close()

    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.requestInterruption()
    worker2.wait(5000)
    assert store2.get_config_value("layout_mode") == "quad"
    assert store2.get_config_value("max_terminals") == "6"


def test_clean_exit_flushes_dirty_data(tmp_path, monkeypatch):
    """退出时 Phase 3 强制 flush：worker 运行中加数据，interrupt → 强制 flush。"""
    _monkeypatch_paths(monkeypatch, tmp_path)
    db = tmp_path / "test.db"
    store = DataStore()
    worker = DataWorker(store, db)
    worker.start()
    worker.msleep(100)  # 等 Phase 1 完成

    store.add_path("C:\\before_exit")
    worker.requestInterruption()
    worker.wait(5000)

    store2 = DataStore()
    worker2 = DataWorker(store2, db)
    worker2.start()
    worker2.requestInterruption()
    worker2.wait(5000)
    assert "C:\\before_exit" in store2.get_paths()


def test_empty_database_starts_clean(tmp_path, monkeypatch):
    """无 JSON 文件、无旧数据库时静默启动。"""
    _monkeypatch_paths(monkeypatch, tmp_path)
    db = tmp_path / "fresh.db"
    store = DataStore()
    worker = DataWorker(store, db)
    worker.start()
    worker.requestInterruption()
    worker.wait(5000)

    assert store.get_paths() == []
    assert store.get_shell_presets_data() == {}
    assert store.get_config_all() == {}


def test_rollback_snapshot_restores_dirty():
    """DataStore: take_snapshot_for_flush 清除 dirty，rollback_snapshot 恢复。"""
    store = DataStore()
    store.add_path("C:\\important")
    assert store.is_any_dirty() is True

    paths, _, _ = store.take_snapshot_for_flush()
    assert paths is not None
    assert store.is_any_dirty() is False  # snapshot 清除了 dirty

    store.rollback_snapshot()
    assert store.is_any_dirty() is True   # rollback 恢复了 dirty
