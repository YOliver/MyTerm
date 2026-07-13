"""DataStore 线程安全内存缓存测试。"""
import threading

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
