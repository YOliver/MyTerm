import logging

from PySide6.QtCore import QThread, Signal
from winpty import PtyProcess

logger = logging.getLogger(__name__)


class TerminalBackend(QThread):
    data_received = Signal(str)
    process_exited = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._columns = 80
        self._rows = 24

    def start_shell(self, cwd=None, columns=80, rows=24, cmdline=None):
        if self.isRunning():
            self.stop()
        self._columns = columns
        self._rows = rows
        if cmdline is None:
            cmdline = ["powershell.exe"]
        logger.info("启动终端: cmd=%s cwd=%s size=%dx%d", cmdline, cwd, columns, rows)
        try:
            self._process = PtyProcess.spawn(
                cmdline,
                cwd=cwd,
                dimensions=(rows, columns),
            )
        except Exception:
            logger.exception("PtyProcess.spawn 失败: cmd=%s cwd=%s", cmdline, cwd)
            raise
        logger.debug("PtyProcess.spawn 成功, pid=%s", getattr(self._process, 'pid', '?'))
        self.start()

    def run(self):
        logger.debug("终端读取循环开始, pid=%s", getattr(self._process, 'pid', '?'))
        try:
            while self._process.isalive():
                data = self._process.read(4096)
                if data:
                    self.data_received.emit(data)
        except EOFError:
            logger.debug("终端 EOF, pid=%s", getattr(self._process, 'pid', '?'))
        except Exception:
            logger.exception("终端读取循环异常, pid=%s", getattr(self._process, 'pid', '?'))
        finally:
            exit_code = 0
            if self._process:
                exit_code = self._process.wait()
            logger.info("终端进程退出, pid=%s exit_code=%d",
                         getattr(self._process, 'pid', '?'), exit_code)
            self.process_exited.emit(exit_code)

    def write(self, text):
        if self._process and self._process.isalive():
            self._process.write(text)

    def resize(self, columns, rows):
        if self._process and self._process.isalive():
            self._process.setwinsize(rows, columns)

    def stop(self):
        pid = getattr(self._process, 'pid', '?') if self._process else None
        alive = self._process.isalive() if self._process else False
        logger.info("停止终端后端: pid=%s, process=%s, alive=%s",
                     pid, self._process is not None, alive)
        if self._process:
            self._process.close()
        if not self.wait(1000):
            logger.warning("终端线程未在 1s 内退出, pid=%s", pid)
