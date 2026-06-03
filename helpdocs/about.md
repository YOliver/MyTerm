# 关于 MyTerm

## 版本与环境信息

| 字段 | 内容 |
|------|------|
| 版本号 | 0.2.2 |
| Commit ID | ba6484037ea111564851a5aaa3e9ff0868010e89 |
| 构建时间 | 2026-06-03 |
| 运行系统 | Windows 10 / 11 (x64) |
| Python 要求 | 3.10+（开发与发版用 3.14） |

## 运行依赖（`requirements.txt`）

| 依赖 | 版本要求 | 用途 |
|------|----------|------|
| PySide6 | >=6.5 | Qt GUI 绑定 |
| pywinpty | >=2.0 | Windows ConPTY 封装 |
| pyte | >=0.8 | ANSI 转义序列解析 |
| wcwidth | >=0.2 | Unicode 宽字符宽度检测 |

## 开发期附加依赖

- `pytest` — 测试框架
- `pyinstaller` — 单文件 EXE 打包
- `pillow` — `scripts/make_icon.py` 生成多尺寸 `icon.ico`
- Inno Setup 6 — 生成 Windows 安装包（中文界面需额外放 `ChineseSimplified.isl`）

## 数据存储位置

- **配置 / 历史**：`%LOCALAPPDATA%\MyTerm\`
- **粘贴图片缓存**：`%LOCALAPPDATA%\MyTerm\Cache\paste\`

> 卸载时不会删除以上数据，保留用户历史。
