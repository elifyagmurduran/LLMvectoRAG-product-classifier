"""Token-bucket rate limiter for API calls (RPM and TPM)."""
from __future__ import annotations
import time
import threading
from src.utils.logging import get_logger

logger = get_logger("pipeline.rate_limiter")


class RateLimiter:
    """Proactive rate limiter using a token-bucket algorithm.

    Tracks two independent budgets — requests per minute (RPM) and tokens
    per minute (TPM).  Before each API call, :meth:`acquire` checks whether
    sending now would exceed either limit and sleeps only the minimum time
    needed.  After the call completes, :meth:`record_usage` deducts the
    actual tokens consumed.

    Thread-safe: uses a lock for all state mutations.

    Args:
        rpm_limit: Maximum requests per minute (0 = unlimited).
        tpm_limit: Maximum tokens per minute (0 = unlimited).
    """

    def __init__(self, rpm_limit: int = 0, tpm_limit: int = 0) -> None:
        self._rpm_limit = rpm_limit
        self._tpm_limit = tpm_limit
        self._request_timestamps: list[float] = []
        self._token_log: list[tuple[float, int]] = []  # (timestamp, tokens)
        self._lock = threading.Lock()

    @property
    def rpm_limit(self) -> int:
        return self._rpm_limit

    @property
    def tpm_limit(self) -> int:
        return self._tpm_limit

    def acquire(self) -> None:
        """Block until a request can be sent within both RPM and TPM limits."""
        while True:
            with self._lock:
                now = time.monotonic()
                self._purge(now)

                rpm_ok = self._rpm_limit == 0 or len(self._request_timestamps) < self._rpm_limit
                tpm_ok = self._tpm_limit == 0 or self._current_tpm() < self._tpm_limit

                if rpm_ok and tpm_ok:
                    self._request_timestamps.append(now)
                    return

                wait = self._wait_time(now)

            logger.debug("Rate limiter: sleeping %.1fs", wait)
            time.sleep(wait)

    def record_usage(self, total_tokens: int) -> None:
        """Record actual token usage after an API call completes."""
        with self._lock:
            self._token_log.append((time.monotonic(), total_tokens))

    # ── internals ─────────────────────────────────────────────────

    def _purge(self, now: float) -> None:
        """Remove entries older than 60 seconds."""
        cutoff = now - 60.0
        self._request_timestamps = [t for t in self._request_timestamps if t > cutoff]
        self._token_log = [(t, n) for t, n in self._token_log if t > cutoff]

    def _current_tpm(self) -> int:
        return sum(n for _, n in self._token_log)

    def _wait_time(self, now: float) -> float:
        """Estimate how long to sleep before a slot opens."""
        waits: list[float] = []
        if self._rpm_limit and len(self._request_timestamps) >= self._rpm_limit:
            oldest = self._request_timestamps[0]
            waits.append(oldest + 60.0 - now)
        if self._tpm_limit and self._current_tpm() >= self._tpm_limit:
            if self._token_log:
                oldest = self._token_log[0][0]
                waits.append(oldest + 60.0 - now)
        return max(min(waits) if waits else 0.1, 0.1)
