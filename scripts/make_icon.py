"""把 icon.png 转成 Windows 多尺寸 icon.ico。

每次替换 icon.png 后跑一次：
    python scripts/make_icon.py

输出 icon.ico 到工程根，会被 spec 与 Inno Setup 引用。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "icon.png"
DST = ROOT / "icon.ico"
SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"找不到源图：{SRC}")
    img = Image.open(SRC)
    img.save(DST, format="ICO", sizes=SIZES)
    print(f"已生成 {DST}（含 {len(SIZES)} 个尺寸）")


if __name__ == "__main__":
    main()
