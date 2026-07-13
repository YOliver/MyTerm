"""JSON → SQLite 迁移测试：幂等性、部分迁移、损坏 JSON 降级。"""
import json
import sqlite3

from store.data_store import DataStore
from store.data_worker import DataWorker


def _monkeypatch_paths(monkeypatch, tmp_path):
    import store.paths as _paths
    monkeypatch.setattr(_paths, "local_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_paths, "is_frozen", lambda: False)


def test_migration_from_json_files(monkeypatch, tmp_path):
    """三个 JSON 文件都存在，首次启动时全部迁移到 SQLite。"""
    _monkeypatch_paths(monkeypatch, tmp_path)

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
    worker.requestInterruption()
    worker.wait(5000)

    assert store.get_paths() == ["C:\\a", "C:\\b"]
    data = store.get_shell_presets_data()
    assert data.get("presets")
    assert store.get_config_value("layout_mode") == "quad"
    assert store.get_config_value("max_terminals") == "6"


def test_migration_idempotent(monkeypatch, tmp_path):
    """第二次启动时不重复迁移（表已有数据，跳过）。"""
    _monkeypatch_paths(monkeypatch, tmp_path)

    (tmp_path / "path_history.json").write_text(
        json.dumps(["C:\\original"]), encoding="utf-8")

    store1 = DataStore()
    w1 = DataWorker(store1, tmp_path / "myterm.db")
    w1.start()
    w1.requestInterruption()
    w1.wait(5000)
    assert store1.get_paths() == ["C:\\original"]

    # 修改 JSON（模拟降级后在旧版中编辑）
    (tmp_path / "path_history.json").write_text(
        json.dumps(["C:\\changed"]), encoding="utf-8")

    store2 = DataStore()
    w2 = DataWorker(store2, tmp_path / "myterm.db")
    w2.start()
    w2.requestInterruption()
    w2.wait(5000)
    assert store2.get_paths() == ["C:\\original"]  # 不是 changed


def test_corrupt_json_skipped(monkeypatch, tmp_path):
    """损坏的 JSON 文件跳过迁移，不阻塞启动。"""
    _monkeypatch_paths(monkeypatch, tmp_path)

    (tmp_path / "path_history.json").write_bytes(b"{not valid")
    (tmp_path / "config.json").write_text(
        json.dumps({"layout_mode": "v"}), encoding="utf-8")

    store = DataStore()
    worker = DataWorker(store, tmp_path / "myterm.db")
    worker.start()
    worker.requestInterruption()
    worker.wait(5000)

    assert store.get_paths() == []  # 损坏文件跳过
    assert store.get_config_value("layout_mode") == "v"  # 正常的迁移成功


def test_no_json_files_starts_clean(monkeypatch, tmp_path):
    """无 JSON 文件时静默启动，不创建 JSON 文件。"""
    _monkeypatch_paths(monkeypatch, tmp_path)

    store = DataStore()
    worker = DataWorker(store, tmp_path / "myterm.db")
    worker.start()
    worker.requestInterruption()
    worker.wait(5000)

    assert store.get_paths() == []
    assert not (tmp_path / "path_history.json").exists()
