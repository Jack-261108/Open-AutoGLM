"""Lightweight console spinner for indicating ongoing model inference."""

from __future__ import annotations

import sys
import threading
import time

_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


class InferenceSpinner:
    """Lightweight TTY-aware spinner that displays ongoing inference status."""

    def __init__(self, message: str = "正在理解屏幕画面并规划动作") -> None:
        self.message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        self._start_time = 0.0

    def start(self) -> None:
        """Start the spinner thread if running in an interactive terminal."""
        if not self._is_tty or self._running:
            return
        self._running = True
        self._start_time = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        idx = 0
        while self._running:
            elapsed = time.monotonic() - self._start_time
            frame = _FRAMES[idx % len(_FRAMES)]
            try:
                sys.stdout.write(f"\r{frame} {self.message}... [{elapsed:.1f}s]")
                sys.stdout.flush()
            except Exception:
                break
            idx += 1
            time.sleep(0.08)

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=0.5)
            self._thread = None
        if self._is_tty:
            try:
                sys.stdout.write("\r\033[K")
                sys.stdout.flush()
            except Exception:
                pass
