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
