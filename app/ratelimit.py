"""本机进程内按 IP 限次。单进程够用；测试里用环境变量关掉。"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = defaultdict(deque)


def enabled() -> bool:
    return os.environ.get("COFFEEBAR_RATE_LIMIT", "1") != "0"


def check(request: Request, name: str, limit: int, window_s: int = 60) -> None:
    if not enabled():
        return
    ip = request.client.host if request.client else "unknown"
    key = f"{name}:{ip}"
    now = time.monotonic()
    q = _hits[key]
    while q and q[0] <= now - window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "试得太勤，过一会儿再来")
    q.append(now)
