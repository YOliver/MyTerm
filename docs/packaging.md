# 打包发布说明

## 一键发布（推荐）

```bat
scripts\release.bat
```

干完三件事：

1. `python scripts/make_icon.py` 把 `icon.png` 转 `icon.ico`
2. `python -m PyInstaller myterm.spec` → `dist/MyTerm.exe`（约 49 MB，单文件）
3. Inno Setup 编译 → `dist/MyTerm-Setup-<version>.exe`

版本号从 `version.py` 读，改一处即可。

## 前置依赖

- Python 3.14 + 工程依赖（`pip install -r requirements.txt`）
- PyInstaller `pip install pyinstaller`
- Pillow `pip install pillow`（生成 .ico 用）
- Inno Setup 6 https://jrsoftware.org/isinfo.php
  默认装到 `C:\Program Files (x86)\Inno Setup 6\`，`release.bat` 会自动找到。

## 单步打包

只想出 exe，不出安装包：

```bash
python -m PyInstaller myterm.spec
```

只想编译已有 exe 的安装包：

```bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 installer\myterm.iss
```

清理重来：

```bash
rm -rf build dist
```

## 安装包行为

- **安装位置**：`%LOCALAPPDATA%\Programs\MyTerm\`（用户级，无 UAC）
- **开始菜单**：`MyTerm` 与 `卸载 MyTerm` 两个快捷方式
- **桌面快捷方式**：不创建
- **卸载入口**：控制面板 → 程序与功能 → MyTerm
- **卸载行为**：只删程序文件，**不动**用户数据（`%APPDATA%\MyTerm`、`%LOCALAPPDATA%\MyTerm`）
- **多语言**：简体中文 + 英文，由系统语言决定默认值

## 运行时目录约定

打包后（`sys.frozen=True`）的文件去向，全部由 `store/paths.py` 解析：

| 用途           | 路径                                          | 说明                       |
| -------------- | --------------------------------------------- | -------------------------- |
| 用户配置       | `%APPDATA%\MyTerm\config.json`                | 跟随域账户漫游             |
| 路径历史       | `%LOCALAPPDATA%\MyTerm\path_history.json`     | 仅本机                     |
| 粘贴图片缓存   | `%LOCALAPPDATA%\MyTerm\Cache\paste\`          | 可随时删                   |
| 迁移哨兵       | `%APPDATA%\MyTerm\.migrated`                  | 标记已迁过，避免重复扫描   |

开发模式（直接 `python main.py`）路径全部仍在工程根，与打包前完全一致，
便于调试与 git 追踪。

## 首启迁移

打包版第一次启动会调用 `migrate_legacy_files()`：

1. 仅 `sys.frozen=True` 触发；开发模式空操作。
2. 若 `%APPDATA%\MyTerm\.migrated` 已存在，直接返回（幂等）。
3. 按优先级 **exe 同目录 → 工程根** 找 `config.json` / `path_history.json`，
   有就 `shutil.copy2` 到 AppData，目标已存在则不覆盖。
4. 无论搬没搬到，最后写空哨兵。

任何 IO 失败都打 stderr，不抛异常、不挡启动。

## 完全重置（开发期手动）

清掉用户数据（含已生成配置）：

```powershell
Remove-Item -Recurse -Force "$env:APPDATA\MyTerm"
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\MyTerm"
```

下次启动会重新创建默认 `config.json`。

## 发布新版流程

1. 改 `version.py` 的 `__version__`
2. `scripts\release.bat`
3. 把 `dist\MyTerm-Setup-<version>.exe` 上传发布渠道

## spec 关键设定

- `console=False`：双击不弹 cmd 窗。临时改 `True` 可看 print/stderr。
- `upx=False`：不压缩。压缩与杀软误报、Qt DLL 启动慢有冲突，体积收益不抵。
- `icon='icon.ico'`：Windows 资源图标。
- `version=...`：把 `version.py` 写进 exe 文件属性，右键属性→详细信息可见。
- `hiddenimports`：`pyte`/`pyte.screens`/`wcwidth`/`winpty` 显式列出防漏。
