import logging
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from store.paths import migrate_legacy_files, resource_path, database_path
from store.log import setup_logging
from store.watchdog import MainThreadWatchdog
from store.data_store import DataStore
from store.data_worker import DataWorker
from ui.main_window import MainWindow
from version import __version__

logger = logging.getLogger(__name__)


ICON_PATH = str(resource_path("icon.png"))


def main():
    """启动顺序：DataStore → DataWorker → MainWindow → QApplication.exec"""
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

    store = DataStore()
    worker = DataWorker(store, database_path())
    window = MainWindow(store)
    worker.data_loaded.connect(window.on_data_loaded)
    worker.start()

    window.show()

    def on_about_to_quit():
        worker.requestInterruption()
        worker.wait(5000)

    app.aboutToQuit.connect(on_about_to_quit)

    # 主线程看门狗：UI 卡死 >=3s 时把主线程调用栈写入日志
    watchdog = MainThreadWatchdog(timeout=3.0, check_interval=1.0)
    watchdog.start(parent=window)

    rc = app.exec()
    logger.info("MyTerm 退出, code=%d", rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
