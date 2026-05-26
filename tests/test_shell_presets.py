"""``store/shell_presets`` 纯逻辑测试：to_argv 翻译表、JSON 持久化与降级链。

测试都通过 ``path=`` 注入 ``tmp_path``，**绝不写真实** ``local_data_dir()``，
否则会污染开发环境的工程根。
"""
from __future__ import annotations

import json

import pytest

from store.shell_presets import (
    ShellPreset,
    SCHEMA_VERSION,
    add_for_installer,
    default_presets,
    load,
    remove_for_installer,
    save,
    to_argv,
)


# ---------------------- to_argv 翻译表 ----------------------

def test_to_argv_powershell():
    assert to_argv("powershell", "claude") == [
        "powershell.exe", "-NoExit", "-Command", "claude",
    ]


def test_to_argv_cmd_uses_slash_K():
    """关键陷阱：必须用 /K 不是 /C，否则命令跑完 cmd 退出会让 tile 黑屏闪退。"""
    argv = to_argv("cmd", "dir")
    assert argv == ["cmd.exe", "/K", "dir"]
    assert "/C" not in argv


def test_to_argv_none_simple():
    assert to_argv("none", "powershell.exe") == ["powershell.exe"]


def test_to_argv_none_with_args():
    assert to_argv("none", "powershell.exe -NoLogo") == ["powershell.exe", "-NoLogo"]


def test_to_argv_none_quoted_path_with_spaces():
    """posix=False：双引号包裹的带空格 Windows 路径要被当成单个 token。"""
    argv = to_argv("none", '"C:\\Program Files\\Git\\bin\\bash.exe" --login')
    # shlex(posix=False) 会保留双引号字面量；只断言反斜杠路径未被吃掉、参数被切出
    assert len(argv) == 2
    assert "Program Files" in argv[0]
    assert "bash.exe" in argv[0]
    assert argv[1] == "--login"


def test_to_argv_unknown_host_falls_back_to_none(capsys):
    argv = to_argv("zsh", "echo hi")
    assert argv == ["echo", "hi"]
    captured = capsys.readouterr()
    assert "未知 host" in captured.err


def test_to_argv_none_empty_returns_empty_list():
    """空命令返回 []，load() 见到会跳过该条。"""
    assert to_argv("none", "") == []
    assert to_argv("none", "   ") == []


# ---------------------- ShellPreset 派生 ----------------------

def test_shell_preset_command_is_computed_from_host():
    p = ShellPreset(label="x", host="powershell", raw_command="claude")
    assert p.command == ["powershell.exe", "-NoExit", "-Command", "claude"]


def test_shell_preset_dataclass_equality_ignores_command():
    """frozen dataclass 相等性不依赖派生字段 command（compare=False）。"""
    a = ShellPreset(label="x", host="cmd", raw_command="dir")
    b = ShellPreset(label="x", host="cmd", raw_command="dir")
    assert a == b


# ---------------------- default_presets ----------------------

def test_default_presets_content():
    presets = default_presets()
    assert len(presets) == 2
    assert presets[0].label == "powershell"
    assert presets[0].host == "none"
    assert presets[0].raw_command == "powershell.exe"
    assert presets[1].label == "cmd"
    assert presets[1].host == "none"
    assert presets[1].raw_command == "cmd.exe"


# ---------------------- load 降级链 ----------------------

def test_load_returns_default_when_missing(tmp_path):
    target = tmp_path / "shell_presets.json"
    presets = load(path=target)
    assert [p.label for p in presets] == ["powershell", "cmd"]
    # 首次启动顺手把默认值落盘了
    assert target.exists()


def test_load_returns_default_when_corrupt(tmp_path, capsys):
    target = tmp_path / "shell_presets.json"
    target.write_bytes(b"{not valid json")
    original = target.read_bytes()

    presets = load(path=target)
    assert [p.label for p in presets] == ["powershell", "cmd"]
    # 关键：坏文件不被覆盖（保护用户手改时的失误）
    assert target.read_bytes() == original
    assert "解析失败" in capsys.readouterr().err


def test_load_returns_default_when_top_level_not_dict(tmp_path):
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    presets = load(path=target)
    assert [p.label for p in presets] == ["powershell", "cmd"]


def test_load_skips_invalid_entry(tmp_path, capsys):
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps({
        "version": 1,
        "presets": [
            {"label": "good", "host": "powershell", "command": "claude"},
            {"label": "", "host": "powershell", "command": "x"},          # label 空
            {"label": "bad-host", "host": "zsh", "command": "x"},          # host 非法
            {"label": "missing-cmd", "host": "powershell"},                 # 缺 command
            "not-a-dict",
            {"label": "empty-cmd", "host": "none", "command": ""},          # to_argv 返回 []
        ],
    }), encoding="utf-8")

    presets = load(path=target)
    assert [p.label for p in presets] == ["good"]
    err = capsys.readouterr().err
    assert "label 缺失或空" in err
    assert "host=" in err
    assert "command 类型错误" in err
    assert "命令为空" in err


def test_load_returns_default_when_all_invalid(tmp_path):
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps({
        "version": 1,
        "presets": [{"label": "x", "host": "zsh", "command": "x"}],
    }), encoding="utf-8")
    presets = load(path=target)
    assert [p.label for p in presets] == ["powershell", "cmd"]


def test_load_returns_default_when_presets_empty(tmp_path):
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps({"version": 1, "presets": []}), encoding="utf-8")
    presets = load(path=target)
    assert [p.label for p in presets] == ["powershell", "cmd"]


# ---------------------- save / roundtrip ----------------------

def test_save_load_roundtrip(tmp_path):
    target = tmp_path / "shell_presets.json"
    original = [
        ShellPreset(label="powershell", host="none", raw_command="powershell.exe"),
        ShellPreset(label="claude",     host="powershell", raw_command="claude"),
        ShellPreset(label="codebuddy",  host="cmd", raw_command="codebuddy"),
    ]
    save(original, path=target)

    loaded = load(path=target)
    assert len(loaded) == 3
    for a, b in zip(original, loaded):
        assert a.label == b.label
        assert a.host == b.host
        assert a.raw_command == b.raw_command
        assert a.command == b.command  # to_argv 派生的也得一致


def test_save_writes_schema_version(tmp_path):
    target = tmp_path / "shell_presets.json"
    save([ShellPreset("x", "none", "x.exe")], path=target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == SCHEMA_VERSION
    assert data["presets"] == [{"label": "x", "host": "none", "command": "x.exe"}]


def test_save_creates_parent_dir(tmp_path):
    """父目录不存在时 save 自动创建（首次启动时 %LOCALAPPDATA%/MyTerm 可能不存在）。"""
    target = tmp_path / "deep" / "nested" / "shell_presets.json"
    save([ShellPreset("x", "none", "x.exe")], path=target)
    assert target.exists()


def test_save_is_atomic_no_tmp_left(tmp_path):
    """正常写入后 .tmp 文件不残留。"""
    target = tmp_path / "shell_presets.json"
    save(default_presets(), path=target)
    leftovers = list(tmp_path.glob("*.tmp"))
    assert leftovers == []


# ---------------------- readonly / installer_id 字段 ----------------------

def test_default_presets_marks_builtins_readonly():
    """内置 powershell / cmd 必须 readonly=True，防误删。"""
    presets = default_presets()
    assert all(p.readonly for p in presets)
    assert all(p.installer_id is None for p in presets)


def test_serialize_omits_default_readonly_and_installer_id(tmp_path):
    """非默认 readonly/installer_id 不写入 json，让普通用户看到的文件最小化。"""
    target = tmp_path / "shell_presets.json"
    save([ShellPreset("x", "none", "x.exe")], path=target)
    data = json.loads(target.read_text(encoding="utf-8"))
    item = data["presets"][0]
    assert "readonly" not in item
    assert "installer_id" not in item


def test_serialize_writes_readonly_and_installer_id_when_set(tmp_path):
    target = tmp_path / "shell_presets.json"
    save([
        ShellPreset("ps", "none", "powershell.exe", readonly=True),
        ShellPreset("claude", "cmd", "claude", installer_id="claude_code"),
    ], path=target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["presets"][0]["readonly"] is True
    assert data["presets"][1]["installer_id"] == "claude_code"


def test_load_legacy_powershell_cmd_promoted_to_readonly(tmp_path):
    """旧版 json（无 readonly 字段）里的内置项升级时自动获得保护。"""
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps({
        "version": 1,
        "presets": [
            {"label": "powershell", "host": "none", "command": "powershell.exe"},
            {"label": "cmd", "host": "none", "command": "cmd.exe"},
            {"label": "claude", "host": "cmd", "command": "claude"},  # 用户手加的，不动
        ],
    }), encoding="utf-8")
    loaded = load(path=target)
    by_label = {p.label: p for p in loaded}
    assert by_label["powershell"].readonly is True
    assert by_label["cmd"].readonly is True
    assert by_label["claude"].readonly is False
    assert by_label["claude"].installer_id is None


def test_load_preserves_installer_id(tmp_path):
    target = tmp_path / "shell_presets.json"
    target.write_text(json.dumps({
        "version": 1,
        "presets": [
            {"label": "claude", "host": "cmd", "command": "claude",
             "installer_id": "claude_code"},
        ],
    }), encoding="utf-8")
    loaded = load(path=target)
    assert loaded[0].installer_id == "claude_code"


def test_save_load_roundtrip_with_new_fields(tmp_path):
    target = tmp_path / "shell_presets.json"
    original = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("claude", "cmd", "claude", installer_id="claude_code"),
        ShellPreset("custom", "powershell", "echo hi"),
    ]
    save(original, path=target)
    loaded = load(path=target)
    assert len(loaded) == 3
    for a, b in zip(original, loaded):
        assert a.readonly == b.readonly
        assert a.installer_id == b.installer_id


# ---------------------- add_for_installer ----------------------

def test_add_for_installer_appends_when_missing():
    presets = default_presets()
    new_list, changed = add_for_installer(
        presets,
        installer_id="claude_code",
        launch={"label": "Claude Code", "host": "cmd", "raw_command": "claude"},
    )
    assert changed is True
    assert len(new_list) == 3
    assert new_list[-1].label == "Claude Code"
    assert new_list[-1].installer_id == "claude_code"
    # 不就地修改入参
    assert len(presets) == 2


def test_add_for_installer_dedup_skips_when_command_already_present():
    """同 raw_command 已存在且已有 installer_id：跳过，changed=False。"""
    presets = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("已有 claude", "cmd", "claude", installer_id="claude_code"),
    ]
    new_list, changed = add_for_installer(
        presets, "claude_code",
        {"label": "Claude Code", "host": "cmd", "raw_command": "claude"},
    )
    assert changed is False
    assert len(new_list) == 2


def test_add_for_installer_adopts_user_added_with_same_command():
    """同 raw_command 已存在但 installer_id=None：补打标记。"""
    presets = [
        ShellPreset("我自己加的", "cmd", "claude"),
    ]
    new_list, changed = add_for_installer(
        presets, "claude_code",
        {"label": "Claude Code", "host": "cmd", "raw_command": "claude"},
    )
    assert changed is True
    assert len(new_list) == 1
    assert new_list[0].label == "我自己加的"  # 保留用户的标签
    assert new_list[0].installer_id == "claude_code"


def test_add_for_installer_invalid_launch_silent_noop(capsys):
    presets = default_presets()
    new_list, changed = add_for_installer(
        presets, "claude_code", {"label": "", "host": "cmd", "raw_command": ""},
    )
    assert changed is False
    assert new_list == presets
    assert "启动项元数据不合法" in capsys.readouterr().err


# ---------------------- remove_for_installer ----------------------

def test_remove_for_installer_removes_matching():
    presets = [
        ShellPreset("powershell", "none", "powershell.exe", readonly=True),
        ShellPreset("Claude Code", "cmd", "claude", installer_id="claude_code"),
        ShellPreset("Codebuddy", "cmd", "codebuddy", installer_id="codebuddy"),
    ]
    new_list, changed = remove_for_installer(presets, "claude_code")
    assert changed is True
    assert [p.label for p in new_list] == ["powershell", "Codebuddy"]


def test_remove_for_installer_keeps_user_added_with_same_command():
    """用户手加的（installer_id=None）即使命令同名也不动。"""
    presets = [
        ShellPreset("我自己加的", "cmd", "claude"),
    ]
    new_list, changed = remove_for_installer(presets, "claude_code")
    assert changed is False
    assert len(new_list) == 1


def test_remove_for_installer_noop_when_not_found():
    presets = default_presets()
    new_list, changed = remove_for_installer(presets, "claude_code")
    assert changed is False
    assert new_list == presets
