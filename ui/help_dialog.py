"""帮助文档对话框：渲染本地内嵌 Markdown。

文件路径由调用方传入（一般来自 ``store.paths.resource_path``），开发态读
工程根，打包态读 PyInstaller 解压目录。文档不存在或读取失败时显示降级
提示，绝不抛异常 —— 帮助菜单不应该有"点了崩"的可能。

样式与 ``EnvCheckDialog`` 各持一份（工程历史习惯，便于各对话框独立演化），
暗色基调与菜单栏 / topbar 一致。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout,
)


_DIALOG_STYLE = (
    "QDialog { background: #1e1e1e; }"
    "QTextBrowser {"
    "  background: #252526; color: #d4d4d4;"
    "  border: 1px solid #3a3a3a;"
    "  font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;"
    "  font-size: 13px;"
    "  padding: 8px 12px;"
    "}"
    # Qt 不支持 a:link/visited 等伪类，链接颜色靠 QTextBrowser 默认或外链浏览器接管。
    "QPushButton {"
    "  font-size: 13px; padding: 6px 18px;"
    "  background: #444; color: #ccc; border: none; border-radius: 3px;"
    "}"
    "QPushButton:hover { background: #555; }"
    "QScrollBar:vertical {"
    "  background: #1e1e1e; width: 12px; margin: 0;"
    "}"
    "QScrollBar::handle:vertical {"
    "  background: #555; border-radius: 6px; min-height: 24px;"
    "}"
    "QScrollBar::handle:vertical:hover { background: #777; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
    "  background: none; border: none; height: 0;"
    "}"
)


class HelpDialog(QDialog):
    """显示一篇 Markdown 文档的滚动对话框。

    构造参数：
    - ``title``：窗口标题，例如 "使用说明"
    - ``md_path``：Markdown 文件绝对路径（``Path`` 或 ``str`` 都行）
    - ``parent``：父窗口

    文件不存在 / 读取失败时不抛异常，而是把错误信息渲染为正文，让用户
    看见"哪里出了问题"而不是窗口闪一下消失。
    """

    def __init__(self, title: str, md_path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 520)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._browser = QTextBrowser(self)
        self._browser.setOpenExternalLinks(True)  # md 里的 http(s) 链接 → 浏览器
        layout.addWidget(self._browser)

        self._load_markdown(Path(md_path))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("关闭", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_markdown(self, path: Path) -> None:
        """读 md 渲染到 browser；失败时降级显示提示，绝不抛异常。"""
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._browser.setMarkdown(
                f"# 文档暂未提供\n\n找不到文件：`{path}`"
            )
            return
        except OSError as e:
            self._browser.setMarkdown(
                f"# 文档读取失败\n\n路径：`{path}`\n\n原因：{e}"
            )
            return
        except UnicodeDecodeError as e:
            self._browser.setMarkdown(
                f"# 文档编码异常\n\n路径：`{path}`\n\n原因：{e}\n\n"
                "请确认文件以 UTF-8 编码保存。"
            )
            return
        self._browser.setMarkdown(text)
        # 加载完滚到顶部（QTextBrowser 默认有时会停在中间）
        self._browser.moveCursor(self._browser.textCursor().MoveOperation.Start)
