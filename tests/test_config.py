import json

import pytest

from store.config import AppConfig, compute_grid_shape
from store.shell_presets import ShellPreset


@pytest.fixture
def isolated_presets(tmp_path, monkeypatch):
    """把 shell_presets 配置文件路径重定向到 tmp_path，避免 AppConfig() 触碰真实
    用户目录 / 工程根。返回该路径，方便测试预先写入配置。"""
    target = tmp_path / "shell_presets.json"
    # 同时 patch 两个模块导出的同名 helper：shell_presets.py 内部调的是
    # `from store.paths import shell_presets_path`，所以 patch 到 paths 模块即可。
    import store.paths
    monkeypatch.setattr(store.paths, "shell_presets_path", lambda: target)
    return target


def test_app_config_loads_from_shell_presets_json(isolated_presets):
    """AppConfig.shell_presets 读自 shell_presets.json；缺失时落默认两条。"""
    cfg = AppConfig()
    assert cfg.max_terminals == 4
    labels = [s.label for s in cfg.shell_presets]
    assert labels == ["powershell", "cmd"]


def test_app_config_reflects_custom_file(isolated_presets):
    isolated_presets.write_text(json.dumps({
        "version": 1,
        "presets": [
            {"label": "claude", "host": "powershell", "command": "claude"},
            {"label": "bash",   "host": "none",       "command": "bash.exe"},
        ],
    }), encoding="utf-8")

    cfg = AppConfig()
    labels = [s.label for s in cfg.shell_presets]
    assert labels == ["claude", "bash"]
    assert cfg.shell_presets[0].command == [
        "powershell.exe", "-NoExit", "-Command", "claude",
    ]


def test_shell_presets_returns_copy_not_alias(isolated_presets):
    cfg = AppConfig()
    a = cfg.shell_presets
    b = cfg.shell_presets
    assert a == b
    assert a is not b  # 防止外部 mutate 串话
    a.clear()
    assert len(cfg.shell_presets) == 2  # 默认两条仍在


def test_shell_preset_command_is_independent_list(isolated_presets):
    """ShellPreset.command 由 to_argv 即时算出，外部修改不污染下一次构造。"""
    cfg = AppConfig()
    first = cfg.shell_presets[0]
    first.command.append("--rogue-arg")
    fresh = AppConfig().shell_presets[0]
    assert "--rogue-arg" not in fresh.command


def test_reload_shell_presets_picks_up_disk_changes(isolated_presets):
    cfg = AppConfig()
    assert [p.label for p in cfg.shell_presets] == ["powershell", "cmd"]

    isolated_presets.write_text(json.dumps({
        "version": 1,
        "presets": [{"label": "only-one", "host": "none", "command": "x.exe"}],
    }), encoding="utf-8")
    cfg.reload_shell_presets()
    assert [p.label for p in cfg.shell_presets] == ["only-one"]


def test_shell_preset_dataclass_equality():
    a = ShellPreset(label="x", host="cmd", raw_command="dir")
    b = ShellPreset(label="x", host="cmd", raw_command="dir")
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


# ── compute_grid_shape_for ──

from store.config import compute_grid_shape_for, LayoutMode  # noqa: E402


def test_compute_grid_shape_for_auto():
    """AUTO 模式与 compute_grid_shape 结果一致。"""
    for n in range(1, 10):
        assert compute_grid_shape_for(n, LayoutMode.AUTO) == compute_grid_shape(n)


def test_compute_grid_shape_for_quad():
    """QUAD 模式固定返回 (2, 2)。"""
    assert compute_grid_shape_for(4, LayoutMode.QUAD) == (2, 2)
    assert compute_grid_shape_for(2, LayoutMode.QUAD) == (2, 2)
    assert compute_grid_shape_for(1, LayoutMode.QUAD) == (2, 2)


def test_compute_grid_shape_for_horizontal():
    """横排模式：rows=1，cols=n（至少 1）。"""
    assert compute_grid_shape_for(4, LayoutMode.HORIZONTAL) == (1, 4)
    assert compute_grid_shape_for(1, LayoutMode.HORIZONTAL) == (1, 1)
    assert compute_grid_shape_for(0, LayoutMode.HORIZONTAL) == (1, 1)


def test_compute_grid_shape_for_vertical():
    """竖排模式：cols=1，rows=n（至少 1）。"""
    assert compute_grid_shape_for(4, LayoutMode.VERTICAL) == (4, 1)
    assert compute_grid_shape_for(1, LayoutMode.VERTICAL) == (1, 1)
    assert compute_grid_shape_for(0, LayoutMode.VERTICAL) == (1, 1)


# ── AppConfig layout_mode 持久化 ──

def test_app_config_layout_mode_default(tmp_path, monkeypatch):
    """无 config.json 时默认 AUTO。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    from store.config import AppConfig
    cfg = AppConfig()
    assert cfg.layout_mode == LayoutMode.AUTO


def test_app_config_layout_mode_persist(tmp_path, monkeypatch):
    """写入 QUAD 后重新加载，layout_mode 不变。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    from store.config import AppConfig, LayoutMode
    cfg = AppConfig()
    cfg.layout_mode = LayoutMode.QUAD
    cfg.save()

    cfg2 = AppConfig()
    assert cfg2.layout_mode == LayoutMode.QUAD


def test_app_config_save_preserves_existing_keys(tmp_path, monkeypatch):
    """save() 不会覆盖 config.json 中已有字段。"""
    import store.paths as _paths
    monkeypatch.setattr(_paths, "data_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(
        '{"max_terminals": 4, "layout_mode": "auto"}', encoding="utf-8",
    )
    from store.config import AppConfig
    cfg = AppConfig()
    cfg.layout_mode = LayoutMode.VERTICAL
    cfg.save()

    saved = tmp_path / "config.json"
    import json
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["layout_mode"] == "v"
    assert data["max_terminals"] == 4
