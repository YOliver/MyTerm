import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from store.paths import migrate_legacy_files
from ui.main_window import MainWindow
from version import __version__


def _resource_path(name: str) -> str:
    """打包模式下读 PyInstaller 的 _MEIPASS 临时目录；开发模式读源码同目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


ICON_PATH = _resource_path("icon.png")


def main():
    # 打包模式首次启动把旧位置的 path_history.json 搬到 LOCALAPPDATA。
    # 开发态空操作，无副作用。
    migrate_legacy_files()

    app = QApplication(sys.argv)
    app.setApplicationName("MyTerm")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("MyTerm")
    app.setStyle("Fusion")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
