"""本机进程内按 IP 限次。单进程够用；测试里用环境变量关掉。"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = defaultdict(deque)

LOGIN_TRIES = 5


def enabled() -> bool:
    return os.environ.get("COFFEEBAR_RATE_LIMIT", "1") != "0"


def client_who(request: Request, source: str | None = None) -> str:
    src = (source or request.headers.get("x-source") or "web").strip().lower()
    if src not in {"web", "mcp"}:
        src = "web"
    ip = request.client.host if request.client else "unknown"
    return f"{src}:{ip}"


def check(
    request: Request,
    name: str,
    limit: int,
    window_s: int = 60,
    who: str | None = None,
    message: str | None = None,
) -> None:
    if not enabled():
        return
    ident = who or (request.client.host if request.client else "unknown")
    key = f"{name}:{ident}"
    now = time.monotonic()
    q = _hits[key]
    while q and q[0] <= now - window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, message or "试得太勤，过一会儿再来")
    q.append(now)
