# MyTerm

> Windows 桌面终端模拟器。

## 开发者

oliveryin，740614279@qq.com

## 简介

MyTerm 是一个轻量的现代 PowerShell 客户端，专注于：

- 真彩色 ANSI 渲染、PowerShell 原生配色
- 多终端平铺（最多 4 个）
- 中文输入法 / 宽字符 / Braille 字体回退
- 路径历史记忆、剪贴板图片粘贴

## 技术栈

- Python + PySide6
- pywinpty（Windows PTY 封装）
- pyte（终端解析）

## 数据存储

- **配置 / 历史**：`%LOCALAPPDATA%\MyTerm\`
- **缓存（粘贴图片等）**：`%LOCALAPPDATA%\MyTerm\Cache\`

卸载时不会删除以上数据，保留用户历史。

## 反馈

待补充。
