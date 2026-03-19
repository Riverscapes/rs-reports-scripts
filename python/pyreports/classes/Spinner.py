"""A simple terminal spinner that displays elapsed time."""

import sys
import threading
import time


class Spinner:
    """Context manager that shows a braille spinner with elapsed seconds.

    Usage::

        with Spinner("Running query"):
            do_something_slow()
    """

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str = "Working"):
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_time: float = 0

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            elapsed = time.time() - self._start_time
            sys.stdout.write(f"\r  {self.CHARS[i % len(self.CHARS)]} {self.message}... {elapsed:.1f}s")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.1)
        elapsed = time.time() - self._start_time
        sys.stdout.write(f"\r  ✔ {self.message} complete in {elapsed:.1f}s\n")
        sys.stdout.flush()

    def __enter__(self):
        self._start_time = time.time()
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self._stop.set()
        if self._thread:
            self._thread.join()
