"""coffeebar 服务入口。单进程：API + 托管前端构建产物。"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import auth, brew as brew_mod
from . import db, ledger, locks, menu, photos, places, ratelimit, spirits, stats, store

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


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_account(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    return auth.require_account(request, conn)


@app.exception_handler(store.Conflict)
async def _conflict(request: Request, exc: store.Conflict):
    return JSONResponse(status_code=409, content={"error": "conflict", "message": str(exc)})


@app.exception_handler(locks.Locked)
async def _locked(request: Request, exc: locks.Locked):
    return JSONResponse(status_code=423, content=exc.detail())


@app.exception_handler(photos.BadPhoto)
async def _bad_photo(request: Request, exc: photos.BadPhoto):
    return JSONResponse(status_code=400, content={"error": "bad_photo", "message": str(exc)})


# ── 账号 ────────────────────────────────────────────────────


def _mail_or_url(to: str, subject: str, url: str, out: dict, key: str) -> None:
    sent = auth.maybe_send(to, subject, f"点开这个链接（{auth.TOKEN_HOURS} 小时内有效）：\n{url}")
    if not sent:
        out[key] = url


@app.post("/api/auth/register", status_code=201)
def api_register(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    ratelimit.check(request, "register", 5)
    account = auth.register(conn, payload.get("email") or "", payload.get("password") or "")
    token = auth.issue_session(conn, account["id"])
    auth.set_cookie(response, token, request)
    out = {
        "id": account["id"],
        "email": account["email"],
        "claimed": account["claimed"],
        "email_verified": account["email_verified"],
    }
    if account.get("verify_token"):
        _mail_or_url(
            account["email"],
            "验证 coffeebar 邮箱",
            auth.link_for(request, "verify", account["verify_token"]),
            out,
            "verify_url",
        )
    return out


@app.post("/api/auth/login")
def api_login(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    ratelimit.check(request, "login", 5)
    account = auth.login(conn, payload.get("email") or "", payload.get("password") or "")
    token = auth.issue_session(conn, account["id"])
    auth.set_cookie(response, token, request)
    return account


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    auth.drop_session(conn, auth.cookie_token(request))
    auth.clear_cookie(response)
    return {"ok": True}


@app.post("/api/auth/forgot")
def api_forgot(payload: dict, request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    ratelimit.check(request, "forgot", 5)
    email = payload.get("email") or ""
    reset_token = auth.request_reset(conn, email)
    out = {"ok": True}
    if reset_token:
        _mail_or_url(
            auth.normalize_email(email),
            "重设 coffeebar 密码",
            auth.link_for(request, "reset", reset_token),
            out,
            "reset_url",
        )
    return out


@app.post("/api/auth/reset")
def api_reset(payload: dict, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    auth.reset_password(conn, payload.get("token") or "", payload.get("password") or "")
    auth.clear_cookie(response)
    return {"ok": True}


@app.post("/api/auth/verify")
def api_verify(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    account = auth.verify_email(conn, payload.get("token") or "")
    token = auth.issue_session(conn, account["id"])
    auth.set_cookie(response, token, request)
    return account


@app.post("/api/auth/resend-verify")
def api_resend_verify(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "forgot", 5)
    if account.get("email_verified"):
        return {"ok": True, "email_verified": True}
    verify_token = auth.issue_token(conn, account["id"], "verify")
    out = {"ok": True, "email_verified": False}
    _mail_or_url(
        account["email"],
        "验证 coffeebar 邮箱",
        auth.link_for(request, "verify", verify_token),
        out,
        "verify_url",
    )
    return out


@app.get("/api/me")
def api_me(account: dict = Depends(current_account)):
    return auth.public_account(account)


@app.post("/api/auth/delete")
def api_delete_me(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    # 只用这一根连接：再 Depends(current_account) 会另开一条，Windows 上删账号容易锁库 500
    account = auth.require_account(request, conn)
    ratelimit.check(request, "delete", 5)
    auth.delete_account(conn, account, payload.get("email") or "", payload.get("password") or "")
    auth.clear_cookie(response)
    return {"ok": True}


# ── 豆子 ────────────────────────────────────────────────────


@app.get("/api/beans")
def api_beans(
    scope: str = "stock",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    beans = store.list_beans(conn, scope, owner_id=account["id"])
    for b in beans:
        dose = stats.average_dose(conn, b["id"])
        b["avg_dose"] = dose
        b["cups_left"] = stats.cups_left(b["balance_g"], dose["avg_g"])
        b["near_empty"] = b["in_stock"] and b["balance_g"] < dose["avg_g"]
        b["cover"] = photos.cover(photos.list_bean_photos(conn, b["id"]))
    return {"beans": beans, "avg_dose": stats.average_dose(conn, owner_id=account["id"])}


@app.post("/api/beans", status_code=201)
def api_create_bean(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    if not payload.get("name", "").strip():
        raise store.Conflict("豆子得有个名字")
    payload = {**payload, "owner_id": account["id"]}
    bean_id = store.create_bean(conn, payload)
    if payload.get("nominal_g"):
        store.add_lot(conn, bean_id, payload)
    return store.get_bean(conn, bean_id, owner_id=account["id"])


@app.get("/api/beans/{bean_id}")
def api_bean(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    bean = store.get_bean(conn, bean_id, owner_id=account["id"])
    if not bean:
        raise HTTPException(404, "没有这支豆")
    bean["photos"] = photos.list_bean_photos(conn, bean_id)
    dose = stats.average_dose(conn, bean_id)
    bean["avg_dose"] = dose
    bean["cups_left"] = stats.cups_left(bean["balance_g"], dose["avg_g"])
    for lot in bean["lots"]:
        lot["cups_left"] = stats.cups_left(lot["balance_g"], dose["avg_g"])
    bean["log"] = store.list_consumption(conn, bean_id=bean_id, owner_id=account["id"], limit=30)
    bean["lock"] = locks.status(conn, f"bean:{bean_id}")
    return bean


@app.patch("/api/beans/{bean_id}")
def api_update_bean(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    store.update_bean(conn, bean_id, payload)
    return store.get_bean(conn, bean_id, owner_id=account["id"])


@app.get("/api/map")
def api_map(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    def cover_of(bean_id: int):
        return photos.cover(photos.list_bean_photos(conn, bean_id))

    return places.map_data(conn, account["id"], cover_of)


@app.put("/api/beans/{bean_id}/places")
def api_set_places(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    try:
        pins = places.set_click_places(conn, bean_id, payload.get("places") or [])
    except places.Conflict as exc:
        raise store.Conflict(str(exc)) from exc
    return {"places": pins}


@app.post("/api/beans/{bean_id}/places/guess")
def api_guess_places(
    bean_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    bean = store.get_bean(conn, bean_id, owner_id=account["id"])
    if not bean:
        raise HTTPException(404, "没有这支豆")
    pins = places.guess_again(conn, bean_id, bean.get("origin"), bean.get("producer"))
    return {"places": pins}


@app.delete("/api/beans/{bean_id}")
def api_delete_bean(
    bean_id: int,
    mode: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    """从豆库拿掉一张卡。有未撤回消耗时带 mode=keep（留下花掉的钱）或 wipe（连记录一起抹）。"""
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    locks.check(conn, f"bean:{bean_id}", x_session, x_source)
    return store.delete_bean(conn, bean_id, mode=mode)


@app.post("/api/beans/{bean_id}/photos", status_code=201)
async def api_add_photo(
    bean_id: int,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("pack"),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """挂一张照片。pack 包装 / tray 豆盘，都可以缺。HEIC 会转成 JPEG。"""
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    return photos.attach_bean_photo(conn, bean_id, kind, await file.read(), file.filename or "")


@app.delete("/api/photos/{photo_id}")
def api_del_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    bean_row = conn.execute("SELECT bean_id FROM bean_photo WHERE id = ?", (photo_id,)).fetchone()
    if bean_row:
        auth.assert_owner(auth.bean_owner(conn, bean_row["bean_id"]), account["id"], "没有这张图")
        photos.delete_bean_photo(conn, photo_id)
        return {"ok": True}
    bottle_row = conn.execute("SELECT bottle_id FROM bottle_photo WHERE id = ?", (photo_id,)).fetchone()
    if bottle_row:
        auth.assert_owner(auth.spirit_owner(conn, bottle_row["bottle_id"]), account["id"], "没有这张图")
        photos.delete_bottle_photo(conn, photo_id)
        return {"ok": True}
    raise HTTPException(404, "没有这张图")


@app.post("/api/beans/{bean_id}/restock-photos", status_code=201)
async def api_add_restock_photo(
    bean_id: int,
    request: Request,
    file: UploadFile = File(...),
    note: str = Form(""),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """补货条目的对照图：货架、淘宝截图、上次那袋都行。"""
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    return photos.attach_restock_photo(conn, bean_id, await file.read(), file.filename or "", note or None)


@app.post("/api/beans/{bean_id}/scores", status_code=201)
def api_add_score(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    store.add_score(conn, bean_id, payload)
    return store.get_bean(conn, bean_id, owner_id=account["id"])


# ── 批次（袋子） ────────────────────────────────────────────


@app.post("/api/beans/{bean_id}/lots", status_code=201)
def api_add_lot(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """再入一袋：只加批次，不新建豆卡。"""
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    lot_id = store.add_lot(conn, bean_id, payload)
    return store.get_lot(conn, lot_id)


@app.post("/api/lots/{lot_id}/open")
def api_open_lot(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """开封：只记日子，不动克数。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    return store.open_lot(conn, lot_id, (payload or {}).get("on"))


@app.post("/api/lots/{lot_id}/measure")
def api_measure(
    lot_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """开袋实称（可选，通常不填）。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    store.set_measured(conn, lot_id, float(payload["measured_g"]))
    return store.get_lot(conn, lot_id)


@app.post("/api/lots/{lot_id}/adjust")
def api_adjust(
    lot_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """中途盘点：输入现在实际还剩多少。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    delta = store.adjust_lot(conn, lot_id, float(payload["actual_g"]), payload.get("note"))
    return {"delta_g": round(delta, 1), "lot": store.get_lot(conn, lot_id)}


@app.post("/api/lots/{lot_id}/close")
def api_close(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """这袋用完：人确认才关，余数记成偏差。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    diff = store.close_lot(conn, lot_id, (payload or {}).get("note"))
    return {"deviation_g": round(diff, 1), "lot": store.get_lot(conn, lot_id)}


@app.post("/api/lots/{lot_id}/writeoff", status_code=201)
def api_writeoff(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """整袋补录：克重和钱进统计，不算一杯、不算到人。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    return store.record_writeoff(conn, lot_id, (payload or {}).get("note"))


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
def api_brew_default(
    bean_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bean_owner(conn, bean_id), account["id"], "没有这支豆")
    store.set_brew_default(
        conn, bean_id, payload.get("method", "v60"),
        float(payload.get("dose_g", 15)), float(payload.get("ratio", 16)),
        payload.get("note"),
    )
    return store.get_bean(conn, bean_id, owner_id=account["id"])


# ── 冲一次 / 撤回 ───────────────────────────────────────────


@app.post("/api/brews", status_code=201)
def api_record_brew(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    """记一次冲煮。lot_id 由人选，amount_g 是当次实际粉量。"""
    lot = store.get_lot(conn, int(payload["lot_id"]))
    if not lot:
        raise HTTPException(404, "没有这一袋")
    auth.assert_owner(auth.bean_owner(conn, lot["bean_id"]), account["id"], "没有这一袋")
    locks.check(conn, f"bean:{lot['bean_id']}", x_session, x_source)
    return store.record_brew(conn, {**payload, "owner_id": account["id"]})


@app.get("/api/consumption")
def api_consumption(
    bean_id: int | None = None,
    person_id: int | None = None,
    limit: int = 50,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {
        "rows": store.list_consumption(
            conn, bean_id=bean_id, person_id=person_id, owner_id=account["id"], limit=limit
        )
    }


@app.post("/api/consumption/{cons_id}/void")
def api_void(
    cons_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """撤回：只划掉不删。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return store.void_consumption(conn, cons_id, (payload or {}).get("reason"))


@app.post("/api/consumption/{cons_id}/unvoid")
def api_unvoid(
    cons_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    store.unvoid_consumption(conn, cons_id)
    return {"ok": True}


@app.delete("/api/consumption/{cons_id}")
def api_delete_voided(
    cons_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """彻底删：只接受已经撤回的行，库存不再动。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return store.delete_voided_consumption(conn, cons_id)


@app.post("/api/consumption/{cons_id}/photos", status_code=201)
async def api_add_consumption_photo(
    cons_id: int,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("bed"),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """给一笔冲煮挂过程照。beans 称豆 / bed 粉床 / finish 冲完 / gear 器具。"""
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    if conn.execute("SELECT id FROM consumption_event WHERE id = ?", (cons_id,)).fetchone():
        auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    return photos.attach_consumption_photo(
        conn, cons_id, kind, await file.read(), file.filename or ""
    )


@app.delete("/api/consumption-photos/{photo_id}")
def api_del_consumption_photo(
    photo_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    row = conn.execute("SELECT cons_id FROM consumption_photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "没有这张图")
    auth.assert_owner(auth.consumption_owner(conn, row["cons_id"]), account["id"], "没有这张图")
    photos.delete_consumption_photo(conn, photo_id)
    return {"ok": True}


@app.post("/api/consumption/{cons_id}/person")
def api_reassign(
    cons_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """人选错了：只改归属，库存不动。"""
    auth.assert_owner(auth.consumption_owner(conn, cons_id), account["id"], "没有这一笔")
    store.reassign_person(conn, cons_id, payload.get("person"), owner_id=account["id"])
    return {"ok": True}


# ── 基酒 ────────────────────────────────────────────────────


@app.get("/api/spirits")
def api_spirits(
    scope: str = "stock",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    items = spirits.list_spirits(conn, scope, owner_id=account["id"])
    for s in items:
        s["cover"] = photos.cover(photos.list_bottle_photos(conn, s["id"]))
    return {"spirits": items, "kinds": spirits.KINDS}


@app.post("/api/spirits", status_code=201)
def api_create_spirit(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    if not payload.get("name", "").strip():
        raise store.Conflict("酒得有个名字")
    payload = {**payload, "owner_id": account["id"]}
    bottle_id = spirits.create_spirit(conn, payload)
    if payload.get("nominal_ml"):
        spirits.add_lot(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@app.get("/api/spirits/{bottle_id}")
def api_spirit(
    bottle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    bottle = spirits.get_spirit(conn, bottle_id, owner_id=account["id"])
    if not bottle:
        raise HTTPException(404, "没有这支酒")
    bottle["photos"] = photos.list_bottle_photos(conn, bottle_id)
    bottle["log"] = store.list_consumption(conn, bottle_id=bottle_id, owner_id=account["id"], limit=30)
    bottle["lock"] = locks.status(conn, f"bottle:{bottle_id}")
    return bottle


@app.patch("/api/spirits/{bottle_id}")
def api_update_spirit(
    bottle_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    locks.check(conn, f"bottle:{bottle_id}", x_session, x_source)
    spirits.update_spirit(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@app.post("/api/spirits/{bottle_id}/lots", status_code=201)
def api_add_bottle_lot(
    bottle_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    locks.check(conn, f"bottle:{bottle_id}", x_session, x_source)
    spirits.add_lot(conn, bottle_id, payload)
    return spirits.get_spirit(conn, bottle_id, owner_id=account["id"])


@app.post("/api/spirits/{bottle_id}/photos", status_code=201)
async def api_add_bottle_photo(
    bottle_id: int,
    request: Request,
    file: UploadFile = File(...),
    kind: str = Form("pack"),
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    ratelimit.check(request, "upload", 20, who=f"acct:{account['id']}")
    auth.assert_owner(auth.spirit_owner(conn, bottle_id), account["id"], "没有这支酒")
    return photos.attach_bottle_photo(conn, bottle_id, kind, await file.read(), file.filename or "")


@app.post("/api/bottle-lots/{lot_id}/open")
def api_open_bottle(
    lot_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    spirits.open_lot(conn, lot_id)
    return spirits.get_lot(conn, lot_id)


@app.post("/api/bottle-lots/{lot_id}/adjust")
def api_adjust_bottle(
    lot_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    return spirits.adjust_lot(conn, lot_id, float(payload["actual_ml"]), payload.get("note"))


@app.post("/api/bottle-lots/{lot_id}/close")
def api_close_bottle(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.bottle_lot_owner(conn, lot_id), account["id"], "没有这一瓶")
    body = payload or {}
    return spirits.close_lot(conn, lot_id, body.get("note"))


@app.post("/api/drinks", status_code=201)
def api_record_drink(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    lot = spirits.get_lot(conn, int(payload["lot_id"]))
    if not lot:
        raise HTTPException(404, "没有这一瓶")
    auth.assert_owner(auth.spirit_owner(conn, lot["bottle_id"]), account["id"], "没有这一瓶")
    return spirits.record_drink(conn, {**payload, "owner_id": account["id"]})


# ── 酒单 / 鸡尾酒 ────────────────────────────────────────────


@app.get("/api/menu")
def api_menu(
    listed_only: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"items": menu.list_menu(conn, account["id"], listed_only=listed_only)}


@app.post("/api/menu", status_code=201)
def api_add_menu_item(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return menu.add_menu_item(conn, {**payload, "owner_id": account["id"]})


@app.patch("/api/menu/{item_id}")
def api_patch_menu_item(
    item_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.menu_item_owner(conn, item_id), account["id"], "没有这条酒单")
    if "listed" in payload:
        return menu.set_listed(conn, item_id, bool(payload["listed"]))
    item = menu.get_item(conn, item_id, account["id"])
    if not item:
        raise HTTPException(404, "没有这条酒单")
    return item


@app.put("/api/menu/order")
def api_reorder_menu(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"items": menu.reorder_menu(conn, account["id"], [int(i) for i in payload.get("ids") or []])}


@app.delete("/api/menu/{item_id}")
def api_delete_menu_item(
    item_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.menu_item_owner(conn, item_id), account["id"], "没有这条酒单")
    menu.delete_menu_item(conn, item_id)
    return {"ok": True}


@app.post("/api/menu/pour", status_code=201)
def api_menu_pour(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    out = menu.pour(
        conn,
        {**payload, "owner_id": account["id"]},
        session_id=x_session,
        source=x_source,
    )
    if out.get("error"):
        return JSONResponse(status_code=200, content=out)
    return out


@app.get("/api/recipes")
def api_recipes(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"recipes": menu.list_recipes(conn, account["id"])}


@app.post("/api/recipes", status_code=201)
def api_create_recipe(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return menu.create_recipe(conn, {**payload, "owner_id": account["id"]})


@app.get("/api/recipes/{recipe_id}")
def api_recipe(
    recipe_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    rec = menu.get_recipe(conn, recipe_id, account["id"])
    if not rec:
        raise HTTPException(404, "没有这个配方")
    rec["lock"] = locks.status(conn, f"recipe:{recipe_id}")
    return rec


@app.patch("/api/recipes/{recipe_id}")
def api_update_recipe(
    recipe_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(menu.recipe_owner(conn, recipe_id), account["id"], "没有这个配方")
    locks.check(conn, f"recipe:{recipe_id}", x_session, x_source)
    return menu.update_recipe(conn, recipe_id, payload)


@app.delete("/api/recipes/{recipe_id}")
def api_delete_recipe(
    recipe_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_owner(menu.recipe_owner(conn, recipe_id), account["id"], "没有这个配方")
    locks.check(conn, f"recipe:{recipe_id}", x_session, x_source)
    menu.delete_recipe(conn, recipe_id)
    return {"ok": True}


@app.get("/api/serves/{serve_id}")
def api_serve(
    serve_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.serve_owner(conn, serve_id), account["id"], "没有这一巡")
    serve = menu.get_serve(conn, serve_id)
    if not serve:
        raise HTTPException(404, "没有这一巡")
    return serve


@app.post("/api/serves/{serve_id}/void")
def api_void_serve(
    serve_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.serve_owner(conn, serve_id), account["id"], "没有这一巡")
    return menu.void_serve(conn, serve_id, (payload or {}).get("reason"))


# ── 人 ──────────────────────────────────────────────────────


@app.get("/api/people")
def api_people(
    include_inactive: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"people": store.list_people(conn, include_inactive, owner_id=account["id"])}


@app.post("/api/people", status_code=201)
def api_add_person(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    pid = store.ensure_person(conn, payload.get("name"), account["id"])
    if pid is None:
        raise store.Conflict("名字不能为空")
    return {"id": pid, "name": payload["name"].strip()}


@app.patch("/api/people/{person_id}")
def api_patch_person(
    person_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(auth.person_owner(conn, person_id), account["id"], "没有这个人")
    if "name" in payload:
        store.rename_person(conn, person_id, payload["name"])
    if "active" in payload:
        store.set_person_active(conn, person_id, bool(payload["active"]))
    return {"people": store.list_people(conn, include_inactive=True, owner_id=account["id"])}


@app.delete("/api/people/{person_id}")
def api_delete_person(
    person_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """删掉这个人。他名下的流水留着，只是变成「没记」。"""
    owner = auth.person_owner(conn, person_id)
    if owner is not None:
        auth.assert_owner(owner, account["id"], "没有这个人")
    out = store.delete_person(conn, person_id)
    return {**out, "people": store.list_people(conn, include_inactive=True, owner_id=account["id"])}


@app.get("/api/people/{person_id}/profile")
def api_profile(
    person_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    profile = stats.person_profile(conn, person_id, owner_id=account["id"])
    if not profile:
        raise HTTPException(404, "没有这个人")
    profile["log"] = store.list_consumption(
        conn, person_id=person_id, owner_id=account["id"], limit=50
    )
    return profile


# ── 统计 / 补货 ─────────────────────────────────────────────


@app.get("/api/stats")
def api_stats(
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return stats.summary(conn, period, owner_id=account["id"])


@app.get("/api/restock")
def api_restock(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"items": stats.restock_list(conn, owner_id=account["id"])}


@app.get("/api/calendar")
def api_calendar(
    year: int | None = None,
    month: int | None = None,
    person_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    now = db.parse(db.now())
    y = year or now.year
    m = month or now.month
    if y < 2000 or y > 2100 or m < 1 or m > 12:
        raise HTTPException(400, "年月不对")
    if person_id is not None:
        row = conn.execute(
            "SELECT id FROM person WHERE id = ? AND owner_id = ?",
            (person_id, account["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这个人")
    return ledger.month(conn, y, m, account["id"], person_id)


@app.get("/api/calendar/day")
def api_calendar_day(
    date: str,
    person_id: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期不对")
    if person_id is not None:
        row = conn.execute(
            "SELECT id FROM person WHERE id = ? AND owner_id = ?",
            (person_id, account["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "没有这个人")
    return ledger.day(conn, date, account["id"], person_id)


@app.get("/api/export")
def api_export(
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    if period not in ("week", "month", "year", "all"):
        raise HTTPException(400, "期间不对")
    raw = ledger.export_zip(conn, account["id"], period)
    name = f"coffeebar-{period}.zip"
    return Response(
        content=raw,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ── 写锁 ────────────────────────────────────────────────────


@app.post("/api/locks/{resource}")
def api_lock(
    resource: str,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
    x_source: str = Header(default="web"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
    body = payload or {}
    return locks.acquire(
        conn, resource, x_session, body.get("holder"), x_source, bool(body.get("take_over"))
    )


@app.put("/api/locks/{resource}")
def api_heartbeat(
    resource: str,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
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
    account: dict = Depends(current_account),
    x_session: str = Header(default="anon"),
):
    auth.assert_lock_resource(conn, resource, account["id"])
    locks.release(conn, resource, x_session)
    return {"ok": True}


@app.get("/api/health")
def api_health(conn: sqlite3.Connection = Depends(get_conn)):
    beans = conn.execute("SELECT COUNT(*) FROM bean").fetchone()[0]
    bottles = conn.execute("SELECT COUNT(*) FROM bottle").fetchone()[0]
    return {"ok": True, "beans": beans, "spirits": bottles, "db": str(db.db_path())}


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
