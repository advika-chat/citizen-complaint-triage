"""Tiny in-memory per-IP sliding-window limiter (single process only)."""
import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)


def limit_per_minute() -> int:
    return int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))


def reset() -> None:
    _hits.clear()


def check_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit_per_minute():
        raise HTTPException(status_code=429, detail="Too many submissions. Please wait a minute and try again.")
    window.append(now)
