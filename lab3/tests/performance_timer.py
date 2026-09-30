from __future__ import annotations

import logging
import time


logger = logging.getLogger(__name__)


class PerformanceTimer:
    """Timer with intermediate checkpoints that does not stop the timer."""

    def __init__(self, name: str = "operation") -> None:
        self.name = name
        self._started_at: float | None = None
        self._last_checkpoint: float | None = None

    def start(self) -> "PerformanceTimer":
        now = time.perf_counter()
        self._started_at = now
        self._last_checkpoint = now
        return self

    def lap(self, label: str = "checkpoint") -> dict[str, float]:
        """Log a checkpoint and return interval and total elapsed time."""
        if self._started_at is None or self._last_checkpoint is None:
            raise RuntimeError("Timer has not been started")

        now = time.perf_counter()
        interval = now - self._last_checkpoint
        total = now - self._started_at
        self._last_checkpoint = now
        logger.info(
            "%s | %s: %.4f s (total: %.4f s)",
            self.name,
            label,
            interval,
            total,
        )
        return {"interval_seconds": interval, "total_seconds": total}

    def stop(self, label: str = "total") -> float:
        """Stop the timer, log the total duration and return it."""
        if self._started_at is None:
            raise RuntimeError("Timer has not been started")

        elapsed = time.perf_counter() - self._started_at
        logger.info("%s | %s: %.4f s", self.name, label, elapsed)
        self._started_at = None
        self._last_checkpoint = None
        return elapsed
