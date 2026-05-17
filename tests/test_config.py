import json

import pytest

from store.config import AppConfig, ShellPreset, compute_grid_shape
from store.config import _DEFAULT_SHELL_PRESETS as DEFAULTS


def _path(tmp_path):
    return str(tmp_path / "config.json")


_DEFAULT_LABELS = [p["label"] for p in DEFAULTS]
_DEFAULT_COUNT = len(DEFAULTS)


def test_creates_default_when_missing(tmp_path):
    p = _path(tmp_path)
    cfg = AppConfig(filepath=p)

    assert cfg.max_terminals == 4
    labels = [s.label for s in cfg.shell_presets]
    assert labels == _DEFAULT_LABELS

    # 文件应被主动写出，便于用户编辑
    with open(p, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["max_terminals"] == 4
    assert len(on_disk["shell_presets"]) == _DEFAULT_COUNT


def test_loads_existing_valid_config(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "max_terminals": 6,
            "shell_presets": [
                {"label": "bash", "command": ["bash"]},
            ],
        }, f)

    cfg = AppConfig(filepath=p)

    assert cfg.max_terminals == 6
    assert cfg.shell_presets == [ShellPreset("bash", ["bash"])]


def test_corrupt_json_falls_back_and_does_not_overwrite(tmp_path):
    p = _path(tmp_path)
    raw = "{这不是合法 JSON"
    with open(p, "w", encoding="utf-8") as f:
        f.write(raw)

    cfg = AppConfig(filepath=p)

    # 内存里用默认值
    assert cfg.max_terminals == 4
    assert len(cfg.shell_presets) == _DEFAULT_COUNT

    # 关键：原文件不能被覆盖，避免吃掉用户辛苦改的内容
    with open(p, "r", encoding="utf-8") as f:
        assert f.read() == raw


def test_max_terminals_clamped_low(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": 0}, f)
    assert AppConfig(filepath=p).max_terminals == 1

    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": -5}, f)
    assert AppConfig(filepath=p).max_terminals == 1


def test_max_terminals_clamped_high(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": 99}, f)

    assert AppConfig(filepath=p).max_terminals == 9


def test_max_terminals_non_int_falls_back(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": "abc"}, f)
    assert AppConfig(filepath=p).max_terminals == 4

    # bool 在 Python 里是 int 的子类，但语义上不该被当作槽位数
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": True}, f)
    assert AppConfig(filepath=p).max_terminals == 4


def test_empty_shell_presets_falls_back(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"shell_presets": []}, f)

    cfg = AppConfig(filepath=p)
    assert len(cfg.shell_presets) == _DEFAULT_COUNT


def test_invalid_preset_items_filtered(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({
            "shell_presets": [
                {"label": "ok", "command": ["bash"]},
                {"label": "no-cmd"},                          # 缺 command
                {"command": ["foo"]},                          # 缺 label
                {"label": "", "command": ["x"]},               # 空 label
                {"label": "bad-cmd", "command": "notalist"},   # command 不是 list
                {"label": "empty-cmd", "command": []},         # command 空
                {"label": "non-str", "command": ["x", 1]},     # argv 含非字符串
                "stringitem",                                  # 类型错
            ],
        }, f)

    cfg = AppConfig(filepath=p)
    assert cfg.shell_presets == [ShellPreset("ok", ["bash"])]


def test_all_presets_invalid_falls_back(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"shell_presets": [{"label": "no-cmd"}]}, f)

    cfg = AppConfig(filepath=p)
    assert len(cfg.shell_presets) == _DEFAULT_COUNT


def test_partial_config_uses_defaults_for_missing(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"max_terminals": 7}, f)  # 没写 shell_presets

    cfg = AppConfig(filepath=p)
    assert cfg.max_terminals == 7
    assert len(cfg.shell_presets) == _DEFAULT_COUNT


def test_root_not_object_falls_back(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as f:
        json.dump([1, 2, 3], f)

    cfg = AppConfig(filepath=p)
    assert cfg.max_terminals == 4
    assert len(cfg.shell_presets) == _DEFAULT_COUNT


@pytest.mark.parametrize("n,expected", [
    (1, (1, 1)),
    (2, (1, 2)),
    (3, (2, 2)),
    (4, (2, 2)),
    (5, (2, 3)),
    (6, (2, 3)),
    (7, (3, 3)),
    (8, (3, 3)),
    (9, (3, 3)),
])
def test_compute_grid_shape(n, expected):
    assert compute_grid_shape(n) == expected
