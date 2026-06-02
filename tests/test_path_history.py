import json
import os
from unittest.mock import patch

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


# ---------------------- 原子写入 ----------------------

def test_save_is_atomic_no_tmp_left(tmp_path):
    """正常保存后 .tmp 文件不残留。"""
    fp = str(tmp_path / "paths.json")
    history = PathHistory(filepath=fp)
    history.add("C:\\a")
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_save_atomic_preserves_old_on_replace_failure(tmp_path):
    """os.replace 失败时，原文件内容不丢失。"""
    fp = str(tmp_path / "paths.json")
    history = PathHistory(filepath=fp)
    history.add("C:\\original")
    original_content = (tmp_path / "paths.json").read_text(encoding="utf-8")

    with patch("store.path_history.os.replace", side_effect=OSError("模拟失败")):
        history.add("C:\\new")

    # 原文件内容应保持不变
    assert (tmp_path / "paths.json").read_text(encoding="utf-8") == original_content


def test_save_atomic_cleans_tmp_on_failure(tmp_path):
    """os.replace 失败后 .tmp 文件应被清理。"""
    fp = str(tmp_path / "paths.json")
    history = PathHistory(filepath=fp)

    with patch("store.path_history.os.replace", side_effect=OSError("模拟失败")):
        history.add("C:\\a")

    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


def test_load_survives_truncated_file(tmp_path):
    """文件被截断（空内容）时，加载返回空列表而非崩溃。"""
    fp = tmp_path / "paths.json"
    fp.write_text("", encoding="utf-8")
    history = PathHistory(filepath=str(fp))
    assert history.all() == []
