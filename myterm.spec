# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：MyTerm onefile + windowed。

构建命令：
    pyinstaller myterm.spec

产物：dist/MyTerm.exe（单文件，无控制台窗口）

依赖说明：
- PySide6 / pywinpty / pyte / wcwidth：PyInstaller 自带 hooks，理论自动发现，
  但显式列入 hiddenimports 防止某些子模块漏掉。
- icon.png + icon.ico 都走 datas/icon 字段；运行期读 icon.png（QIcon 多尺寸友好），
  exe 文件本身用 icon.ico 做 Windows 资源。
"""
import os
import glob
import winpty as _winpty_pkg

# 单一版本号源，避免 spec 与 main.py 漂移
_version_globals = {}
with open(os.path.join(os.path.dirname(os.path.abspath(SPEC)), 'version.py'), encoding='utf-8') as _f:
    exec(_f.read(), _version_globals)
APP_VERSION = _version_globals['__version__']

# 把 "0.1.0" 转成 (0, 1, 0, 0)，PyInstaller 的 VSVersionInfo 要四元组
_v_parts = [int(x) for x in APP_VERSION.split('.')]
while len(_v_parts) < 4:
    _v_parts.append(0)
APP_VERSION_TUPLE = tuple(_v_parts[:4])


from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
    StringStruct, VarFileInfo, VarStruct,
)

version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=APP_VERSION_TUPLE,
        prodvers=APP_VERSION_TUPLE,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,        # VOS_NT_WINDOWS32
        fileType=0x1,      # VFT_APP
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable('040904B0', [  # 0x0409 = en-US, 0x04B0 = Unicode
                StringStruct('CompanyName', 'MyTerm'),
                StringStruct('FileDescription', 'MyTerm 终端模拟器'),
                StringStruct('FileVersion', APP_VERSION),
                StringStruct('InternalName', 'MyTerm'),
                StringStruct('OriginalFilename', 'MyTerm.exe'),
                StringStruct('ProductName', 'MyTerm'),
                StringStruct('ProductVersion', APP_VERSION),
            ]),
        ]),
        VarFileInfo([VarStruct('Translation', [0x0409, 0x04B0])]),
    ],
)


block_cipher = None


# pywinpty 的 native 旁路文件：winpty.dll / conpty.dll / winpty-agent.exe / OpenConsole.exe
# PyInstaller 没有官方 hook-winpty，.pyd 能被自动收但这 4 个 .dll/.exe 不会。
# 缺它们的话子进程一启动就报 -1073741510 (0xC000013A)。
# 必须放进 EXE 同级（dest='winpty'），让 pywinpty 的 ptyprocess.py 能在 winpty 包目录里找到。
_winpty_dir = os.path.dirname(_winpty_pkg.__file__)
_winpty_binaries = []
for _pat in ('*.dll', '*.exe'):
    for _f in glob.glob(os.path.join(_winpty_dir, _pat)):
        _winpty_binaries.append((_f, 'winpty'))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_winpty_binaries,
    datas=[
        ('icon.png', '.'),
    ],
    hiddenimports=[
        'pyte',
        'pyte.screens',
        'wcwidth',
        'winpty',  # pywinpty 实际包名
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 单元测试 / 文档 / 工程内不参与运行的目录
        'tests',
        'docs',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MyTerm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # 不用 UPX：与杀软误报和 Qt dll 冲突的概率比体积收益大
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # GUI，不要 cmd 窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
    version=version_resource,
)
