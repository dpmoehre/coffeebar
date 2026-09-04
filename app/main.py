"""coffeebar 服务入口。单进程：API + 托管前端构建产物。"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import brew as brew_mod
from . import db, locks, photos, stats, store

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    yield


app = FastAPI(title="coffeebar", version="0.1.0", lifespan=lifespan)


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


@app.exception_handler(store.Conflict)
async def _conflict(request: Request, exc: store.Conflict):
    return JSONResponse(status_code=409, content={"error": "conflict", "message": str(exc)})


@app.exception_handler(locks.Locked)
async def _locked(request: Request, exc: locks.Locked):
    return JSONResponse(status_code=423, content=exc.detail())


@app.exception_handler(photos.BadPhoto)
async def _bad_photo(request: Request, exc: photos.BadPhoto):
    return JSONResponse(status_code=400, content={"error": "bad_photo", "message": str(exc)})


# ── 豆子 ────────────────────────────────────────────────────


@app.get("/api/beans")
def api_beans(scope: str = "stock", conn: sqlite3.Connection = Depends(get_conn)):
    beans = store.list_beans(conn, scope)
    for b in beans:
        dose = stats.average_dose(conn, b["id"])
        b["avg_dose"] = dose
        b["cups_left"] = stats.cups_left(b["balance_g"], dose["avg_g"])
        b["near_empty"] = b["in_stock"] and b["balance_g"] < dose["avg_g"]
        b["cover"] = photos.cover(photos.list_bean_photos(conn, b["id"]))
    return {"beans": beans, "avg_dose": stats.average_dose(conn)}


@app.post("/api/beans", status_code=201)
def api_create_bean(payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    if not payload.get("name", "").strip():
        raise store.Conflict("豆子得有个名字")
    bean_id = store.create_bean(conn, payload)
    if payload.get("nominal_g"):
        store.add_lot(conn, bean_id, payload)
    return store.get_bean(conn, bean_id)


@app.get("/api/beans/{bean_id}")
def api_bean(bean_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    bean = store.get_bean(conn, bean_id)
    if not bean:
        raise HTTPException(404, "没有这支豆")
    bean["photos"] = photos.list_bean_photos(conn, bean_id)
    dose = stats.average_dose(conn, bean_id)
    bean["avg_dose"] = dose
    bean["cups_left"] = stats.cups_left(bean["balance_g"], dose["avg_g"])
    for lot in bean["lots"]:
        lot["cups_left"] = stats.cups_left(lot["balance_g"], dose["avg_g"])
    bean["log"] = store.list_consumption(conn, bean_id=bean_id, limit=30)
    bean["lock"] = locks.status(conn, f"bean:{bean_id}")
    return bean


@app.patch("/api/beans/{bean_id}")
def api_update_bean(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    store.update_bean(conn, bean_id, payload)
    return store.get_bean(conn, bean_id)


@app.post("/api/beans/{bean_id}/photos", status_code=201)
async def api_add_photo(
    bean_id: int,
    file: UploadFile = File(...),
    kind: str = Form("pack"),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """挂一张照片。pack 包装 / tray 豆盘，都可以缺。HEIC 会转成 JPEG。"""
    if not store.get_bean(conn, bean_id):
        raise HTTPException(404, "没有这支豆")
    return photos.attach_bean_photo(conn, bean_id, kind, await file.read(), file.filename or "")


@app.delete("/api/photos/{photo_id}")
def api_del_photo(photo_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    photos.delete_bean_photo(conn, photo_id)
    return {"ok": True}


@app.post("/api/beans/{bean_id}/restock-photos", status_code=201)
async def api_add_restock_photo(
    bean_id: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """补货条目的对照图：货架、淘宝截图、上次那袋都行。"""
    if not store.get_bean(conn, bean_id):
        raise HTTPException(404, "没有这支豆")
    return photos.attach_restock_photo(conn, bean_id, await file.read(), file.filename or "", note or None)


@app.post("/api/beans/{bean_id}/scores", status_code=201)
def api_add_score(bean_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    store.add_score(conn, bean_id, payload)
    return store.get_bean(conn, bean_id)


# ── 批次（袋子） ────────────────────────────────────────────


@app.post("/api/beans/{bean_id}/lots", status_code=201)
def api_add_lot(bean_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    """再入一袋：只加批次，不新建豆卡。"""
    if not store.get_bean(conn, bean_id):
        raise HTTPException(404, "没有这支豆")
    lot_id = store.add_lot(conn, bean_id, payload)
    return store.get_lot(conn, lot_id)


@app.post("/api/lots/{lot_id}/open")
def api_open_lot(lot_id: int, payload: dict | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    """开封：只记日子，不动克数。"""
    return store.open_lot(conn, lot_id, (payload or {}).get("on"))


@app.post("/api/lots/{lot_id}/measure")
def api_measure(lot_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    """开袋实称（可选，通常不填）。"""
    store.set_measured(conn, lot_id, float(payload["measured_g"]))
    return store.get_lot(conn, lot_id)


@app.post("/api/lots/{lot_id}/adjust")
def api_adjust(lot_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    """中途盘点：输入现在实际还剩多少。"""
    delta = store.adjust_lot(conn, lot_id, float(payload["actual_g"]), payload.get("note"))
    return {"delta_g": round(delta, 1), "lot": store.get_lot(conn, lot_id)}


@app.post("/api/lots/{lot_id}/close")
def api_close(lot_id: int, payload: dict | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    """这袋用完：人确认才关，余数记成偏差。"""
    diff = store.close_lot(conn, lot_id, (payload or {}).get("note"))
    return {"deviation_g": round(diff, 1), "lot": store.get_lot(conn, lot_id)}


# ── 冲煮 ────────────────────────────────────────────────────


@app.get("/api/brew/plan")
def api_brew_plan(
    method: str = "v60",
    dose_g: float = brew_mod.DEFAULT_DOSE,
    ratio: float = brew_mod.DEFAULT_RATIO,
):
    """按当场输入的粉量与比例算方案。不落库。"""
    return brew_mod.plan(method, dose_g, ratio)


@app.get("/api/brew/methods")
def api_brew_methods():
    return {"methods": [{"key": k, "label": v} for k, v in brew_mod.METHODS.items()]}


@app.post("/api/beans/{bean_id}/brew-default")
def api_brew_default(bean_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    store.set_brew_default(
        conn, bean_id, payload.get("method", "v60"),
        float(payload.get("dose_g", 15)), float(payload.get("ratio", 16)),
        payload.get("note"),
    )
    return store.get_bean(conn, bean_id)


# ── 冲一次 / 撤回 ───────────────────────────────────────────


@app.post("/api/brews", status_code=201)
def api_record_brew(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    """记一次冲煮。lot_id 由人选，amount_g 是当次实际粉量。"""
    lot = store.get_lot(conn, int(payload["lot_id"]))
    if not lot:
        raise HTTPException(404, "没有这一袋")
    locks.check(conn, f"bean:{lot['bean_id']}", x_session, x_source)
    return store.record_brew(conn, payload)


@app.get("/api/consumption")
def api_consumption(
    bean_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_conn),
):
    return {"rows": store.list_consumption(conn, bean_id, person_id, limit)}


@app.post("/api/consumption/{cons_id}/void")
def api_void(cons_id: int, payload: dict | None = None, conn: sqlite3.Connection = Depends(get_conn)):
    """撤回：只划掉不删。"""
    return store.void_consumption(conn, cons_id, (payload or {}).get("reason"))


@app.post("/api/consumption/{cons_id}/unvoid")
def api_unvoid(cons_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    store.unvoid_consumption(conn, cons_id)
    return {"ok": True}


@app.post("/api/consumption/{cons_id}/person")
def api_reassign(cons_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    """人选错了：只改归属，库存不动。"""
    store.reassign_person(conn, cons_id, payload.get("person"))
    return {"ok": True}


# ── 人 ──────────────────────────────────────────────────────


@app.get("/api/people")
def api_people(include_inactive: bool = False, conn: sqlite3.Connection = Depends(get_conn)):
    return {"people": store.list_people(conn, include_inactive)}


@app.post("/api/people", status_code=201)
def api_add_person(payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    pid = store.ensure_person(conn, payload.get("name"))
    if pid is None:
        raise store.Conflict("名字不能为空")
    return {"id": pid, "name": payload["name"].strip()}


@app.patch("/api/people/{person_id}")
def api_patch_person(person_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_conn)):
    if "name" in payload:
        store.rename_person(conn, person_id, payload["name"])
    if "active" in payload:
        store.set_person_active(conn, person_id, bool(payload["active"]))
    return {"people": store.list_people(conn, include_inactive=True)}


@app.delete("/api/people/{person_id}")
def api_delete_person(person_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    """删掉这个人。他名下的流水留着，只是变成「没记」。"""
    out = store.delete_person(conn, person_id)
    return {**out, "people": store.list_people(conn, include_inactive=True)}


@app.get("/api/people/{person_id}/profile")
def api_profile(person_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    profile = stats.person_profile(conn, person_id)
    if not profile:
        raise HTTPException(404, "没有这个人")
    profile["log"] = store.list_consumption(conn, person_id=person_id, limit=50)
    return profile


# ── 统计 / 补货 ─────────────────────────────────────────────


@app.get("/api/stats")
def api_stats(period: str = "month", conn: sqlite3.Connection = Depends(get_conn)):
    return stats.summary(conn, period)


@app.get("/api/restock")
def api_restock(conn: sqlite3.Connection = Depends(get_conn)):
    return {"items": stats.restock_list(conn)}


# ── 写锁 ────────────────────────────────────────────────────


@app.post("/api/locks/{resource}")
def api_lock(
    resource: str,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    body = payload or {}
    return locks.acquire(
        conn, resource, x_session, body.get("holder"), x_source, bool(body.get("take_over"))
    )


@app.put("/api/locks/{resource}")
def api_heartbeat(
    resource: str,
    conn: sqlite3.Connection = Depends(get_conn),
    x_session: str = Header(default="anon"),
):
    ok = locks.heartbeat(conn, resource, x_session)
    if not ok:
        return JSONResponse(
            status_code=409,
            content={"error": "taken_over", "message": "已被其他窗口接管，你这次的修改没有保存"},
        )
    return {"ok": True}


@app.delete("/api/locks/{resource}")
def api_unlock(
    resource: str,
    conn: sqlite3.Connection = Depends(get_conn),
    x_session: str = Header(default="anon"),
):
    locks.release(conn, resource, x_session)
    return {"ok": True}


@app.get("/api/health")
def api_health(conn: sqlite3.Connection = Depends(get_conn)):
    beans = conn.execute("SELECT COUNT(*) FROM bean").fetchone()[0]
    return {"ok": True, "beans": beans, "db": str(db.db_path())}


# ── 照片与前端构建产物（放最后，别盖住 /api） ───────────────

db.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=db.PHOTO_DIR), name="photos")

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
