"""剪贴板图片落盘与路径格式化测试。

QImage 是纯数据类，构造与 save 都不依赖 QApplication，因此整个测试不需要
pytest-qt 也不会启动 GUI。
"""
from __future__ import annotations

import os
from datetime import datetime

import pytest
from PySide6.QtGui import QImage

from store.clipboard_image import format_path_for_pty, save_clipboard_image


def _make_image(width: int = 4, height: int = 4) -> QImage:
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(0xFF8800)  # 任意填充色，保证不是 null
    return img


def test_save_normal_image(tmp_path):
    img = _make_image()
    path = save_clipboard_image(img, str(tmp_path))
    assert path is not None
    assert os.path.isfile(path)
    # 文件可被 QImage 读回，证明确实是合法 PNG
    reloaded = QImage(path)
    assert not reloaded.isNull()
    assert reloaded.width() == 4
    assert reloaded.height() == 4


def test_save_creates_missing_dir(tmp_path):
    img = _make_image()
    nested = tmp_path / "a" / "b" / "paste_cache"
    assert not nested.exists()
    path = save_clipboard_image(img, str(nested))
    assert path is not None
    assert nested.is_dir()
    assert os.path.dirname(path) == str(nested.resolve()) or \
           os.path.normcase(os.path.dirname(path)) == os.path.normcase(str(nested))


def test_save_null_image_returns_none(tmp_path):
    null_img = QImage()
    assert null_img.isNull()
    assert save_clipboard_image(null_img, str(tmp_path)) is None


def test_filename_uses_injected_time(tmp_path):
    img = _make_image()
    now = datetime(2026, 5, 18, 15, 30, 12, 123_456)
    path = save_clipboard_image(img, str(tmp_path), now=now)
    assert path is not None
    assert os.path.basename(path) == "paste_20260518_153012_123.png"


def test_filenames_differ_within_same_second(tmp_path):
    img = _make_image()
    # 同秒不同毫秒 → 文件名不同
    paths = [
        save_clipboard_image(img, str(tmp_path), now=datetime(2026, 5, 18, 15, 30, 12, ms * 1000))
        for ms in (1, 2, 999)
    ]
    assert all(p is not None for p in paths)
    assert len({os.path.basename(p) for p in paths}) == 3


@pytest.mark.parametrize("raw,expected", [
    # 反斜杠转正斜杠
    (r"G:\a\b.png", '"G:/a/b.png" '),
    # 含空格的路径——双引号让 shell 不会拆词
    (r"G:\My Stuff\paste.png", '"G:/My Stuff/paste.png" '),
    # 已经是正斜杠 → 幂等
    ("G:/a/b.png", '"G:/a/b.png" '),
    # Unix 风格也能跑（虽然实际用不到，但函数应该健壮）
    ("/tmp/x.png", '"/tmp/x.png" '),
])
def test_format_path_for_pty(raw, expected):
    assert format_path_for_pty(raw) == expected
