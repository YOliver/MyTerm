import pytest

from store.config import AppConfig, ShellPreset, SHELL_PRESETS_RAW, compute_grid_shape


def test_app_config_loads_module_constants():
    cfg = AppConfig()
    assert cfg.max_terminals == 4
    labels = [s.label for s in cfg.shell_presets]
    assert labels == [label for label, _ in SHELL_PRESETS_RAW]


def test_shell_presets_returns_copy_not_alias():
    cfg = AppConfig()
    a = cfg.shell_presets
    b = cfg.shell_presets
    assert a == b
    assert a is not b  # 防止外部 mutate 串话
    a.clear()
    assert len(cfg.shell_presets) == len(SHELL_PRESETS_RAW)


def test_shell_preset_command_is_independent_list():
    """构造时应 deep-copy command list，外部修改不污染配置。"""
    cfg = AppConfig()
    first = cfg.shell_presets[0]
    first.command.append("--rogue-arg")
    fresh = AppConfig().shell_presets[0]
    assert "--rogue-arg" not in fresh.command


def test_shell_preset_dataclass_equality():
    a = ShellPreset("x", ["a", "b"])
    b = ShellPreset("x", ["a", "b"])
    assert a == b


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
