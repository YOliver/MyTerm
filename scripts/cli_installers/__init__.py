"""CLI 安装脚本集合。

每个 ``.py`` 文件（``_`` 开头的私有模块除外）就是一个可安装的 CLI 项。
模块需提供以下约定接口（详见 ``_base.py``）：

- 常量：``ID``、``NAME``、``DESCRIPTION``、``REQUIRES``
- ``LAUNCH``（可选 dict）：``{"label", "host", "raw_command"}``，
  安装成功后自动添加到 AI CLI 配置；未声明则不添加
- ``detect() -> tuple[bool, str]``：探测是否已安装，返回 (是否已装, 版本/详情)
- ``install() -> Iterator[InstallEvent]``：执行安装，yield 实时输出与最终退出码
- ``uninstall() -> Iterator[InstallEvent]``（可选）：执行卸载；未提供时 UI 隐藏卸载按钮

发现器在 ``store/cli_installers.py`` 实现，UI 通过它拿到全部条目。

新增一个 CLI = 在本目录丢一个 ``.py`` 文件，无需改动 UI 或 spec。
"""
