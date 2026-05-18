"""剪贴板图片落盘与命令行路径格式化。

设计为不依赖 widget 的纯函数，便于单元测试（QImage 本身是纯数据类，
构造无需 QApplication）。

使用场景：在终端 widget 检测到剪贴板含图片时，把 QImage 落盘成 PNG，
再把双引号包裹的绝对路径写进 PTY，让 claude/codebuddy 等 CLI 可以读图。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QImage


def save_clipboard_image(
    image: "QImage",
    cache_dir: str,
    now: datetime | None = None,
) -> str | None:
    """把 QImage 落盘为 PNG，返回绝对路径；失败返回 None。

    - cache_dir 不存在时自动创建（含父目录）
    - 文件名 paste_YYYYMMDD_HHMMSS_<毫秒>.png，毫秒位避免同秒冲突
    - image.isNull() → None
    - QImage.save() 失败 → None
    - now 为 None 时使用 datetime.now()，注入是为了测试可控
    """
    if image.isNull():
        return None

    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        return None

    if now is None:
        now = datetime.now()
    # 取毫秒前 3 位，文件名比微秒短且足够区分
    ms = now.microsecond // 1000
    filename = f"paste_{now.strftime('%Y%m%d_%H%M%S')}_{ms:03d}.png"
    abs_path = os.path.abspath(os.path.join(cache_dir, filename))

    if not image.save(abs_path, "PNG"):
        return None
    return abs_path


def format_path_for_pty(absolute_path: str) -> str:
    """把绝对路径包成 `"<path>" ` 形式，便于直接写进 PTY 命令行。

    - 反斜杠统一转正斜杠（Windows shell 两种都吃，正斜杠免去转义烦恼）
    - 末尾保留一个空格，方便用户接着输入提示词
    - 不加换行，让命令行保持在同一行等用户继续编辑
    """
    normalized = absolute_path.replace("\\", "/")
    return f'"{normalized}" '
