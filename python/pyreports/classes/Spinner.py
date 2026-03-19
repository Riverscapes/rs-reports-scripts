"""A simple terminal spinner that displays elapsed time."""

import sys
import threading
import time
from termcolor import colored


class Spinner:
    """Context manager that shows a braille spinner with elapsed seconds.

    Usage::

        with Spinner("Running query"):
            do_something_slow()
    """

    CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str = "Working", complete_message: str = "Complete"):
        self.message = message
        self.complete_message = complete_message
        self._stop = threading.Event()
        self._failed = False
        self._thread: threading.Thread | None = None
        self._start_time: float = 0

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            elapsed = time.time() - self._start_time
            sys.stdout.write(colored(f"\r  {self.CHARS[i % len(self.CHARS)]} {self.message}... {elapsed:.1f}s", 'cyan'))
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.1)
        elapsed = time.time() - self._start_time
        if self._failed:
            sys.stdout.write(colored(f"\r  ❌ {self.message} failed after {elapsed:.1f}s\n", 'red'))
        else:
            complete_message = self.complete_message or self.message
            sys.stdout.write(colored(f"\r  ✅ {complete_message} in {elapsed:.1f}s\n", 'green'))
        sys.stdout.flush()

    def __enter__(self):
        self._start_time = time.time()
        self._stop.clear()
        self._failed = False
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self._failed = _exc_type is not None
        self._stop.set()
        if self._thread:
            self._thread.join()
