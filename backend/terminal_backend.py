from PySide6.QtCore import QThread, Signal
from winpty import PtyProcess


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
        self._process = PtyProcess.spawn(
            cmdline,
            cwd=cwd,
            dimensions=(rows, columns),
        )
        self.start()

    def run(self):
        try:
            while self._process.isalive():
                data = self._process.read(4096)
                if data:
                    self.data_received.emit(data)
        except EOFError:
            pass
        finally:
            exit_code = 0
            if self._process:
                exit_code = self._process.wait()
            self.process_exited.emit(exit_code)

    def write(self, text):
        if self._process and self._process.isalive():
            self._process.write(text)

    def resize(self, columns, rows):
        if self._process and self._process.isalive():
            self._process.setwinsize(rows, columns)

    def stop(self):
        if self._process:
            self._process.close()
        self.wait(1000)
