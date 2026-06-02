import logging
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from store.paths import migrate_legacy_files, resource_path
from store.log import setup_logging
from ui.main_window import MainWindow
from version import __version__

logger = logging.getLogger(__name__)


ICON_PATH = str(resource_path("icon.png"))


def main():
    # 打包模式首次启动把旧位置的 path_history.json 搬到 LOCALAPPDATA。
    # 开发态空操作，无副作用。
    migrate_legacy_files()
    setup_logging()
    logger.info("MyTerm %s 启动 (Python %s)", __version__, sys.version.split()[0])

    app = QApplication(sys.argv)
    app.setApplicationName("MyTerm")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("MyTerm")
    app.setStyle("Fusion")
    if os.path.exists(ICON_PATH):
        app.setWindowIcon(QIcon(ICON_PATH))
    window = MainWindow()
    window.show()
    rc = app.exec()
    logger.info("MyTerm 退出, code=%d", rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
