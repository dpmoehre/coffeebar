"""coffeebar 服务入口。单进程：API + 托管前端构建产物。

路由按领域挂在 app/routers/，这里只负责启动、异常和静态文件。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, db, locks, photos, places, spirits, store
from .routers import mount

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_db(conn)
    spirits.backfill_kinds(conn)
    places.backfill(conn)
    conn.close()
    yield


app = FastAPI(title="coffeebar", version="0.1.0", lifespan=lifespan)
mount(app)


@app.exception_handler(store.Conflict)
async def _conflict(request: Request, exc: store.Conflict):
    body = {"error": "conflict", "message": str(exc)}
    if getattr(exc, "extra", None):
        body.update(exc.extra)
    return JSONResponse(status_code=409, content=body)


@app.exception_handler(locks.Locked)
async def _locked(request: Request, exc: locks.Locked):
    return JSONResponse(status_code=423, content=exc.detail())


@app.exception_handler(photos.BadPhoto)
async def _bad_photo(request: Request, exc: photos.BadPhoto):
    return JSONResponse(status_code=400, content={"error": "bad_photo", "message": str(exc)})


@app.exception_handler(auth.OrphansPending)
async def _orphans_pending(request: Request, exc: auth.OrphansPending):
    return JSONResponse(
        status_code=400,
        content={"error": "orphans", "message": str(exc), **exc.counts},
    )


class PhotoFiles(StaticFiles):
    """文件名是 uuid，改过就换名。让浏览器把封面留下，返回列表不用再穿隧道。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if getattr(response, "status_code", 0) == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


db.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/photos", PhotoFiles(directory=db.PHOTO_DIR), name="photos")

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = WEB_DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
