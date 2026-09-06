"""HTTP：豆子、袋子、冲煮方案。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile

from .. import auth, brew as brew_mod, gear, locks, photos, places, ratelimit, stats, store
from ..deps import current_account, get_conn, optional_account

router = APIRouter()


# ── 豆子 ────────────────────────────────────────────────────


@router.get("/api/beans")
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


@router.get("/api/beans/similar")
def api_similar_beans(
    name: str | None = None,
    origin: str | None = None,
    process: str | None = None,
    roast: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """同账号查重。只读，最多 5 张。重名仍允许再建，由人决定。"""
    return {
        "beans": store.find_similar_beans(
            conn,
            account["id"],
            name=name,
            origin=origin,
            process=process,
            roast=roast,
        )
    }


@router.post("/api/beans", status_code=201)
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


@router.get("/api/beans/{bean_id}")
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
    bean["grind_hint"] = store.grind_hint_for_bean(conn, bean_id)
    return bean


@router.patch("/api/beans/{bean_id}")
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
    before = store.get_bean(conn, bean_id, owner_id=account["id"])
    store.update_bean(conn, bean_id, payload)
    bean = store.get_bean(conn, bean_id, owner_id=account["id"])
    if before and before.get("certified_at") and bean and not bean.get("certified_at"):
        bean["certification_dropped"] = True
    return bean


@router.get("/api/map")
def api_map(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    def cover_of(bean_id: int):
        return photos.cover(photos.list_bean_photos(conn, bean_id))

    return places.map_data(conn, account["id"], cover_of)


@router.put("/api/beans/{bean_id}/places")
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
    bean = store.get_bean(conn, bean_id, owner_id=account["id"])
    return {"places": pins, "certification_dropped": bool(bean and not bean.get("certified"))}


@router.post("/api/beans/{bean_id}/places/guess")
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
    bean = store.get_bean(conn, bean_id, owner_id=account["id"])
    return {"places": pins, "certification_dropped": bool(bean and not bean.get("certified"))}


@router.delete("/api/beans/{bean_id}")
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


@router.post("/api/beans/{bean_id}/photos", status_code=201)
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


@router.delete("/api/photos/{photo_id}")
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


@router.post("/api/beans/{bean_id}/restock-photos", status_code=201)
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


@router.post("/api/beans/{bean_id}/scores", status_code=201)
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


@router.post("/api/beans/{bean_id}/lots", status_code=201)
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


@router.patch("/api/lots/{lot_id}")
def api_patch_lot(
    lot_id: int,
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """后补或改烘焙日。只改日子，不写库存事件。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    if "roasted_on" not in payload:
        raise store.Conflict("只能改烘焙日")
    return store.set_lot_roasted_on(conn, lot_id, payload.get("roasted_on"))


@router.post("/api/lots/{lot_id}/open")
def api_open_lot(
    lot_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    """开封：只记日子，不动克数。"""
    auth.assert_owner(auth.lot_bean_owner(conn, lot_id), account["id"], "没有这一袋")
    return store.open_lot(conn, lot_id, (payload or {}).get("on"))


@router.post("/api/lots/{lot_id}/measure")
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


@router.post("/api/lots/{lot_id}/adjust")
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


@router.post("/api/lots/{lot_id}/close")
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


@router.post("/api/lots/{lot_id}/writeoff", status_code=201)
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


@router.get("/api/brew/plan")
def api_brew_plan(
    method: str = "v60",
    dose_g: float = brew_mod.DEFAULT_DOSE,
    ratio: float = brew_mod.DEFAULT_RATIO,
):
    """按当场输入的粉量与比例算方案。不落库。"""
    return brew_mod.plan(method, dose_g, ratio)


@router.get("/api/brew/methods")
def api_brew_methods(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict | None = Depends(optional_account),
):
    owner = account["id"] if account else None
    return {
        "methods": gear.annotate_methods(conn, owner),
        "filter": gear.filter_teaser(conn, owner),
    }


@router.post("/api/beans/{bean_id}/brew-default")
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
