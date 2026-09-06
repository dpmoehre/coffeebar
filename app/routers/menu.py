"""HTTP：酒单与配方。"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import auth, locks, menu, store
from ..deps import current_account, get_conn

router = APIRouter()


# ── 酒单 / 鸡尾酒 ────────────────────────────────────────────


@router.get("/api/menu")
def api_menu(
    listed_only: bool = False,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"items": menu.list_menu(conn, account["id"], listed_only=listed_only)}


@router.post("/api/menu", status_code=201)
def api_add_menu_item(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return menu.add_menu_item(conn, {**payload, "owner_id": account["id"]})


@router.patch("/api/menu/{item_id}")
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


@router.put("/api/menu/order")
def api_reorder_menu(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"items": menu.reorder_menu(conn, account["id"], [int(i) for i in payload.get("ids") or []])}


@router.delete("/api/menu/{item_id}")
def api_delete_menu_item(
    item_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.menu_item_owner(conn, item_id), account["id"], "没有这条酒单")
    menu.delete_menu_item(conn, item_id)
    return {"ok": True}


@router.post("/api/menu/pour", status_code=201)
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


@router.get("/api/recipes")
def api_recipes(
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return {"recipes": menu.list_recipes(conn, account["id"])}


@router.post("/api/recipes", status_code=201)
def api_create_recipe(
    payload: dict,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    return menu.create_recipe(conn, {**payload, "owner_id": account["id"]})


@router.get("/api/recipes/{recipe_id}")
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


@router.patch("/api/recipes/{recipe_id}")
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


@router.delete("/api/recipes/{recipe_id}")
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


@router.get("/api/serves/{serve_id}")
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


@router.post("/api/serves/{serve_id}/void")
def api_void_serve(
    serve_id: int,
    payload: dict | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    account: dict = Depends(current_account),
):
    auth.assert_owner(menu.serve_owner(conn, serve_id), account["id"], "没有这一巡")
    return menu.void_serve(conn, serve_id, (payload or {}).get("reason"))

