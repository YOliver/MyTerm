"""环境检测纯逻辑测试。

UI（EnvCheckDialog/EnvCheckWorker）依赖 Qt 事件循环不在此覆盖。
真实子进程调用只用 python 自身做正向 smoke（系统必装），其他工具不依赖。
"""
from __future__ import annotations

import pytest

from store.env_check import EnvSpec, check_one, parse_version


@pytest.mark.parametrize("output,pattern,expected", [
    # node 风格："v22.13.0\n"
    ("v22.13.0\n", r"v?(\d+\.\d+\.\d+)", "22.13.0"),
    # npm 风格："10.8.2\n"
    ("10.8.2\n", r"(\d+\.\d+\.\d+)", "10.8.2"),
    # python 风格："Python 3.14.3"
    ("Python 3.14.3", r"Python\s+(\d+\.\d+\.\d+)", "3.14.3"),
    # git 风格："git version 2.47.0.windows.1"——只取前三段
    ("git version 2.47.0.windows.1", r"git\s+version\s+(\d+\.\d+\.\d+)", "2.47.0"),
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
