"""单一版本号源。

发布新版只改这一处：
- ``main.py`` 通过 ``QApplication.applicationVersion`` 暴露给 Qt。
- ``myterm.spec`` 嵌入到 ``MyTerm.exe`` 的 Windows 文件属性。
- ``installer/myterm.iss`` 通过 ``#define`` 取，决定安装包文件名与注册表中显示版本。
- ``scripts/release.bat`` 用它命名 ``MyTerm-Setup-x.y.z.exe``。
"""

__version__ = "0.1.4"
