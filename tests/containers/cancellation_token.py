import os
import threading


class CancellationToken:
    """Flag to signal a thread it should cancel itself.
    This cooperative cancellation pattern is commonly used in c# and go
    See https://learn.microsoft.com/en-us/dotnet/api/system.threading.cancellationtoken?view=net-9.0
    """

    def __init__(self):
        # consider using the wrapt.synchronized decorator
        # https://github.com/GrahamDumpleton/wrapt/blob/develop/blog/07-the-missing-synchronized-decorator.md
        self._lock = threading.Lock()
        self._canceled = False
        # something selectable avoids having to use short timeout in select
        self._read_fd, self._write_fd = os.pipe()

    def fileno(self):
        """This lets us use the token in select() calls"""
        return self._read_fd

    @property
    def cancelled(self):
        with self._lock:
            return self._canceled

    def cancel(self):
        with self._lock:
            os.write(self._write_fd, b'x')
            self._canceled = True

    def __del__(self):
        # consider https://docs.python.org/3/library/weakref.html#weakref.finalize
        with self._lock:
            os.close(self._read_fd)
            os.close(self._write_fd)
