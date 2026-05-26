"""环境检测纯逻辑测试。

UI（EnvCheckDialog/EnvCheckWorker）依赖 Qt 事件循环不在此覆盖。
真实子进程调用只用 python 自身做正向 smoke（系统必装），其他工具不依赖。
"""
from __future__ import annotations

import pytest

from store.env_check import EnvSpec, _decode_output, check_one, parse_version


@pytest.mark.parametrize("output,pattern,expected", [
    # node 风格："v22.13.0\n"
    ("v22.13.0\n", r"v?(\d+\.\d+\.\d+)", "22.13.0"),
    # npm 风格："10.8.2\n"
    ("10.8.2\n", r"(\d+\.\d+\.\d+)", "10.8.2"),
    # python 风格："Python 3.14.3"
    ("Python 3.14.3", r"Python\s+(\d+\.\d+\.\d+)", "3.14.3"),
    # pip 风格："pip 26.1.1 from C:\...\site-packages\pip (python 3.14)"——后面的 3.14 不能误当版本
    (
        "pip 26.1.1 from C:\\Users\\foo\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\pip (python 3.14)",
        r"pip\s+(\d+\.\d+\.\d+)",
        "26.1.1",
    ),
    # git 风格："git version 2.47.0.windows.1"——只取前三段
    ("git version 2.47.0.windows.1", r"git\s+version\s+(\d+\.\d+\.\d+)", "2.47.0"),
    # claude-internal 风格：版本号嵌在欢迎语前一行（中文冒号 + 后续含其他版本号干扰）
    (
        "版本号: 1.1.7\n\n欢迎使用 Claude Code Internal\n参考 https://example/2.3.4",
        r"版本号[:：]\s*(\d+\.\d+\.\d+)",
        "1.1.7",
    ),
    # claude-internal 风格：兼容英文/全角冒号
    ("版本号：9.0.1\n", r"版本号[:：]\s*(\d+\.\d+\.\d+)", "9.0.1"),
    # 不命中
    ("hello world", r"(\d+\.\d+\.\d+)", None),
    # 空输出
    ("", r"(\d+\.\d+\.\d+)", None),
])
def test_parse_version(output, pattern, expected):
    assert parse_version(output, pattern) == expected


def test_check_one_command_not_found():
    """工具不存在：installed=False，其他字段 None，不抛异常。"""
    spec = EnvSpec(
        name="FakeTool",
        command="definitely_not_a_real_command_xyz_2026",
        version_args=["--version"],
        version_pattern=r"(\d+\.\d+\.\d+)",
    )
    result = check_one(spec)
    assert result.name == "FakeTool"
    assert result.installed is False
    assert result.version is None
    assert result.path is None
    assert result.error is None


def test_check_one_real_python():
    """用 python 自己做正向 smoke：installed=True，version 与 path 都有值。

    这测试在缺 python 的机器上不可能跑（pytest 本身就要 python），所以可靠。
    """
    spec = EnvSpec(
        name="Python",
        command="python",
        version_args=["--version"],
        version_pattern=r"Python\s+(\d+\.\d+\.\d+)",
    )
    result = check_one(spec)
    assert result.installed is True
    assert result.path is not None
    assert result.version is not None
    # 版本号至少形如 X.Y.Z
    parts = result.version.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
    assert result.error is None


def test_decode_output_utf8():
    """UTF-8 字节正常解码，中文不丢。"""
    raw = "版本号: 1.1.7\n".encode("utf-8")
    assert _decode_output(raw) == "版本号: 1.1.7\n"


def test_decode_output_gbk_fallback():
    """纯 GBK 字节（非合法 UTF-8）回退到 GBK，中文仍可读。"""
    raw = "版本: 2.3.4".encode("gbk")
    # 这串字节不是合法 UTF-8（含 0x80+ 但不符合 UTF-8 续字节规则）
    decoded = _decode_output(raw)
    assert "版本" in decoded
    assert "2.3.4" in decoded


def test_decode_output_pure_ascii():
    """纯 ASCII 输出（如 codebuddy --version 的 '2.97.3\\n'）UTF-8 路径直接命中。"""
    assert _decode_output(b"2.97.3\n") == "2.97.3\n"


def test_decode_output_replaces_invalid():
    """既不是合法 UTF-8 也不是合法 GBK 的字节序列：用 replace 兜底，不抛异常。"""
    # 0xFF 在 UTF-8 / GBK 里都不是合法起始字节
    result = _decode_output(b"\xff\xfe abc")
    assert "abc" in result  # 至少 ASCII 部分能保留
