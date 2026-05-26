"""CLI 安装项发现器与底层 run_command 测试。

不依赖 Qt，纯逻辑层覆盖：
- run_command：流式 stdout、退出码、找不到命令的兜底
- discover：能列出 claude_code 这一首个真实条目
- claude_code.detect：在 claude 不存在时不抛异常
"""
from __future__ import annotations

import sys

import pytest

from scripts.cli_installers._base import InstallEvent, run_command
from scripts.cli_installers import claude_code
from store.cli_installers import InstallerSpec, discover


# ----------------------------- run_command -----------------------------

def test_run_command_command_not_found():
    """命令不存在时 yield 一行 stderr + exit(127)，不抛异常。"""
    events = list(run_command(["definitely_not_a_real_cmd_xyz_2026"]))
    # 至少有一条 stderr + 一条 exit
    kinds = [e.kind for e in events]
    assert "stderr" in kinds
    assert events[-1].kind == "exit"
    assert events[-1].returncode == 127


def test_run_command_streams_stdout_and_exit_zero():
    """跑一个一定能找到的命令（python 自身）：能拿到 stdout 行 + exit(0)。

    用 ``python -c "print('hello')"`` 而不是 ``cmd /c echo``，
    后者在非 Windows 平台不可移植；前者在所有跑 pytest 的环境里都能用。
    """
    events = list(run_command([sys.executable, "-c", "print('hello-from-test')"]))
    stdout_texts = [e.text for e in events if e.kind == "stdout"]
    assert any("hello-from-test" in t for t in stdout_texts), stdout_texts
    assert events[-1].kind == "exit"
    assert events[-1].returncode == 0


def test_run_command_nonzero_exit():
    """命令本身能跑但退出码非 0：returncode 透传。"""
    events = list(run_command([sys.executable, "-c", "import sys; sys.exit(3)"]))
    assert events[-1].kind == "exit"
    assert events[-1].returncode == 3


# ----------------------------- discover -----------------------------

def test_discover_returns_claude_code():
    """发现器至少能列出 claude_code，且字段完整、回调可调用。"""
    specs = discover()
    by_id = {s.id: s for s in specs}
    assert "claude_code" in by_id, f"已发现: {list(by_id)}"

    spec = by_id["claude_code"]
    assert isinstance(spec, InstallerSpec)
    assert spec.name == "Claude Code"
    assert "npm" in spec.requires
    assert callable(spec.detect)
    assert callable(spec.install)


def test_discover_skips_underscore_modules():
    """``_base`` 是私有基础模块，不应被当作安装项暴露给 UI。"""
    specs = discover()
    assert all(s.id != "_base" for s in specs)


def test_discover_sorted_by_id():
    """返回顺序按 id 字典序，UI 渲染稳定。"""
    specs = discover()
    ids = [s.id for s in specs]
    assert ids == sorted(ids)


# ----------------------------- claude_code.detect -----------------------------

def test_claude_code_detect_no_throw_when_missing(monkeypatch):
    """``claude`` 不在 PATH 时返回 (False, "")，不抛异常。"""
    # 强制 shutil.which 返回 None：无论用户机器装没装 claude 都可靠
    monkeypatch.setattr("scripts.cli_installers.claude_code.shutil.which", lambda _: None)
    installed, detail = claude_code.detect()
    assert installed is False
    assert detail == ""


def test_claude_code_detect_handles_subprocess_error(monkeypatch):
    """``claude --version`` 抛 OSError 时降级为未安装，不向上抛。"""
    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.shutil.which",
        lambda _: "/fake/path/claude",
    )

    def _raise(*_a, **_kw):
        raise OSError("simulated")

    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.subprocess.run", _raise)
    installed, detail = claude_code.detect()
    assert installed is False
    assert detail == ""


def test_claude_code_detect_parses_version(monkeypatch):
    """正向：subprocess 返回版本字符串，detect 取首行。"""

    class _Result:
        returncode = 0
        stdout = "1.0.123 (Claude Code)\n"
        stderr = ""

    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.shutil.which",
        lambda _: "/fake/path/claude",
    )
    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.subprocess.run",
        lambda *a, **kw: _Result(),
    )
    installed, detail = claude_code.detect()
    assert installed is True
    assert "1.0.123" in detail


# ----------------------------- claude_code.install -----------------------------

def test_claude_code_install_yields_info_and_npm_call(monkeypatch):
    """install() 先 yield 一条 info，再把 run_command 的事件透传。

    把 run_command 替换成假实现，验证调用参数 + 事件流式透传。
    """
    captured_cmd: list[list[str]] = []

    def _fake_run_command(cmd, cwd=None):
        captured_cmd.append(list(cmd))
        yield InstallEvent("stdout", "fake-line-1")
        yield InstallEvent("exit", "", returncode=0)

    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.run_command", _fake_run_command
    )

    events = list(claude_code.install())
    kinds = [e.kind for e in events]
    assert kinds[0] == "info"
    assert "stdout" in kinds
    assert events[-1].kind == "exit" and events[-1].returncode == 0

    assert captured_cmd == [["npm", "i", "-g", "@anthropic-ai/claude-code"]]


def test_claude_code_uninstall_calls_npm_uninstall(monkeypatch):
    """uninstall() 走 npm uninstall -g 路径，事件流与 install 同结构。"""
    captured_cmd: list[list[str]] = []

    def _fake_run_command(cmd, cwd=None):
        captured_cmd.append(list(cmd))
        yield InstallEvent("stdout", "removed")
        yield InstallEvent("exit", "", returncode=0)

    monkeypatch.setattr(
        "scripts.cli_installers.claude_code.run_command", _fake_run_command
    )

    events = list(claude_code.uninstall())
    kinds = [e.kind for e in events]
    assert kinds[0] == "info"
    assert events[-1].kind == "exit" and events[-1].returncode == 0
    assert captured_cmd == [["npm", "uninstall", "-g", "@anthropic-ai/claude-code"]]


def test_discover_exposes_uninstall_when_present():
    """claude_code 模块定义了 uninstall，发现器应把它暴露在 InstallerSpec.uninstall。"""
    specs = discover()
    spec = next(s for s in specs if s.id == "claude_code")
    assert spec.uninstall is not None
    assert callable(spec.uninstall)


def test_discover_exposes_launch_when_declared():
    """claude_code 声明了 LAUNCH，发现器应把字典原样透传到 spec.launch。"""
    specs = discover()
    spec = next(s for s in specs if s.id == "claude_code")
    assert spec.launch is not None
    # 与模块里 LAUNCH = {"label": "Claude Code", "host": "cmd", "raw_command": "claude"} 对齐
    assert spec.launch.get("label") == "Claude Code"
    assert spec.launch.get("host") == "cmd"
    assert spec.launch.get("raw_command") == "claude"


def test_discover_invalid_launch_is_ignored(monkeypatch, capsys):
    """LAUNCH 缺键时整个字段降为 None，不影响其它字段加载。"""
    from scripts.cli_installers import claude_code as _cc
    # 故意把 LAUNCH 改坏（缺 raw_command）
    monkeypatch.setattr(_cc, "LAUNCH", {"label": "X", "host": "cmd"})

    specs = discover()
    spec = next(s for s in specs if s.id == "claude_code")
    assert spec.launch is None
    assert "LAUNCH 格式不合法" in capsys.readouterr().err
