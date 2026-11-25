"""Per-person rate limits, kept in memory so there is no extra service to run.

Each person's recent uses are remembered for as long as the longest limit needs. The counters restart with the server, and each server
process counts on its own. That is right for one process (how this app runs) but not for several behind a load balancer.
"""
import math
import threading
import time
from collections import deque
from typing import NamedTuple

SWEEP_AT = 1000  # when this many people are remembered, the ones not seen for a whole window are forgotten


class Refused(NamedTuple):
    wait: int  # seconds until one more use is allowed
    window: int  # the window that said no, in seconds
    most: int  # how many uses that window allows


def wait_text(seconds: int) -> str:
    """12 -> "12 seconds", 90 -> "2 minutes", 7300 -> "3 hours". Rounded up, so it is never too short."""
    minutes = math.ceil(seconds / 60)
    count, unit = (seconds, "second") if seconds < 60 else (minutes, "minute") if minutes < 60 else (math.ceil(seconds / 3600), "hour")
    return f"{count} {unit}" + ("" if count == 1 else "s")


class RateLimiter:
    """Counts uses per key (a user id) in sliding windows. A use that is refused is not counted."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock  # the tests swap in a clock they can move
        self.uses: dict[str, deque[float]] = {}
        self.lock = threading.Lock()  # the routes run in several threads at once

    def take(self, key: str, limits: dict[int, int]) -> Refused | None:
        """Count one use for `key`. `limits` maps a window in seconds to the most uses allowed in it (0 = no limit).
        Returns None when the use is allowed, otherwise the window that refused it and how long to wait."""
        limits = {window: most for window, most in limits.items() if most > 0}
        if not limits:
            return None
        now, longest = self.clock(), max(limits)
        with self.lock:
            if len(self.uses) >= SWEEP_AT:
                for stale in [k for k, seen in self.uses.items() if not seen or now - seen[-1] >= longest]:
                    del self.uses[stale]
            seen = self.uses.setdefault(key, deque())
            while seen and now - seen[0] >= longest:
                seen.popleft()
            refused = None
            for window, most in limits.items():
                inside = [t for t in seen if now - t < window]
                if len(inside) >= most:
                    wait = max(1, math.ceil(inside[len(inside) - most] + window - now))  # when enough old uses have left this window
                    if refused is None or wait > refused.wait:
                        refused = Refused(wait, window, most)
            if refused is None:
                seen.append(now)
            return refused

    def give_back(self, key: str) -> None:
        """Undo the latest use, for a request that got no answer through no fault of the person."""
        with self.lock:
            if self.uses.get(key):
                self.uses[key].pop()

    def reset(self) -> None:
        with self.lock:
            self.uses.clear()
