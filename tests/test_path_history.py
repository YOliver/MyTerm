from unittest.mock import patch

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


# ---------------------- 写入 ----------------------

def test_save_writes_directly_no_tmp(tmp_path):
    """直接写入正式文件，不产生 .tmp 残留。"""
    fp = str(tmp_path / "paths.json")
    history = PathHistory(filepath=fp)
    history.add("C:\\a")
    assert list(tmp_path.glob("*.tmp")) == []
    assert (tmp_path / "paths.json").exists()


def test_save_swallows_oserror(tmp_path):
    """写入失败（OSError）时不抛异常、不崩溃，内存状态仍更新。"""
    fp = str(tmp_path / "paths.json")
    history = PathHistory(filepath=fp)

    with patch("store.path_history.json.dump", side_effect=OSError("模拟失败")):
        history.add("C:\\a")  # 不应抛出

    # 落盘失败不影响内存中的历史
    assert history.all() == ["C:\\a"]


def test_load_survives_truncated_file(tmp_path):
    """文件被截断（空内容）时，加载返回空列表而非崩溃。"""
    fp = tmp_path / "paths.json"
    fp.write_text("", encoding="utf-8")
    history = PathHistory(filepath=str(fp))
    assert history.all() == []
