"""按领域挂 API。顺序和原先 main.py 一致，避免 {id} 抢掉更具体的路径。"""

from fastapi import FastAPI

from . import admin_http, auth, beans, brews, gear, kingdom, menu, ops, people, plaza, spirits, stats, writelocks


def mount(app: FastAPI) -> None:
    for mod in (
        auth, beans, gear, brews, spirits, menu, people, stats,
        writelocks, kingdom, plaza, admin_http, ops,
    ):
        app.include_router(mod.router)
