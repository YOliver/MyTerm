import pytest
from store.path_history import PathHistory


def test_add_and_get_recent(tmp_path):
    history = PathHistory(filepath=str(tmp_path / "test.json"))
    history.add("C:\\Users")
    history.add("C:\\Windows")

    paths = history.all()
    assert paths == ["C:\\Windows", "C:\\Users"]


def test_dedup_moves_to_top(tmp_path):
    history = PathHistory(filepath=str(tmp_path / "test.json"))
    history.add("C:\\Users")
    history.add("C:\\Windows")
    history.add("C:\\Users")

    paths = history.all()
    assert paths == ["C:\\Users", "C:\\Windows"]


def test_max_ten_entries(tmp_path):
    history = PathHistory(filepath=str(tmp_path / "test.json"))
    for i in range(15):
        history.add(f"C:\\path{i}")

    paths = history.all()
    assert len(paths) == 10
    assert paths[0] == "C:\\path14"


def test_empty_history_returns_empty_list(tmp_path):
    history = PathHistory(filepath=str(tmp_path / "empty.json"))
    assert history.all() == []


def test_persist_and_load(tmp_path):
    history_a = PathHistory(filepath=str(tmp_path / "paths.json"))
    history_a.add("C:\\test")

    history_b = PathHistory(filepath=str(tmp_path / "paths.json"))
    assert history_b.all() == ["C:\\test"]
