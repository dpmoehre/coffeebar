"""HTTP：账号、会话、整库导出。"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .. import auth, backup, ratelimit
from ..deps import current_account, get_conn

router = APIRouter()


# ── 账号 ────────────────────────────────────────────────────


@router.get("/api/auth/config")
def api_auth_config():
    return {"invite_required": auth.invite_required()}


def _mail_or_url(to: str, subject: str, url: str, out: dict, key: str) -> None:
    sent = auth.maybe_send(to, subject, f"点开这个链接（{auth.TOKEN_HOURS} 小时内有效）：\n{url}")
    if not sent:
        out[key] = url


@router.post("/api/auth/register", status_code=201)
def api_register(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    ratelimit.check(request, "register", 5)
    account = auth.register(
        conn,
        payload.get("email") or "",
        payload.get("password") or "",
        payload.get("invite"),
        payload.get("claim"),
    )
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


@router.post("/api/auth/login")
def api_login(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        account = auth.login(conn, payload.get("email") or "", payload.get("password") or "")
    except HTTPException as exc:
        if exc.status_code == 401:
            ratelimit.check(
                request,
                "login",
                ratelimit.LOGIN_TRIES,
                who=ratelimit.client_who(request),
                message="登录试错已经 5 次，过一分钟再来",
            )
        raise
    token = auth.issue_session(conn, account["id"])
    auth.set_cookie(response, token, request)
    return account


@router.post("/api/auth/logout")
def api_logout(request: Request, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    auth.drop_session(conn, auth.cookie_token(request))
    auth.clear_cookie(response)
    return {"ok": True}


@router.post("/api/auth/forgot")
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


@router.post("/api/auth/reset")
def api_reset(payload: dict, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
    auth.reset_password(conn, payload.get("token") or "", payload.get("password") or "")
    auth.clear_cookie(response)
    return {"ok": True}


@router.post("/api/auth/verify")
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


@router.post("/api/auth/resend-verify")
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


@router.get("/api/me")
def api_me(request: Request, conn: sqlite3.Connection = Depends(get_conn)):
    account = auth.require_account(request, conn)
    return {**auth.public_account(account), **auth.stock_flags(conn, account["id"])}


@router.post("/api/auth/claim-orphans")
def api_claim_orphans(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
):
    account = auth.require_account(request, conn)
    return auth.claim_now(conn, account)


@router.post("/api/auth/password")
def api_change_password(
    payload: dict,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
):
    account = auth.require_account(request, conn)
    try:
        auth.change_password(conn, account, payload.get("old") or "", payload.get("new") or "")
    except HTTPException as exc:
        if exc.status_code == 401:
            ratelimit.check(request, "password", ratelimit.LOGIN_TRIES, who=ratelimit.client_who(request))
        raise
    auth.drop_other_sessions(conn, account["id"], auth.cookie_token(request))
    return {"ok": True}


@router.post("/api/auth/delete")
def api_delete_me(
    payload: dict,
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
):
    # 只用这一根连接：再 Depends(current_account) 会另开一条，Windows 上删账号容易锁库 500
    account = auth.require_account(request, conn)
    ratelimit.check(request, "delete", 5)
    auth.delete_account(
        conn,
        account,
        payload.get("email") or "",
        payload.get("password") or "",
        payload.get("export_token"),
    )
    auth.clear_cookie(response)
    return {"ok": True}


@router.get("/api/ops/backup")
def api_ops_backup(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
):
    account = auth.require_account(request, conn)
    if not auth.is_stock_account(conn, account["id"]):
        raise HTTPException(403, "空号不用下整库")
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    path = Path(tmp.name)
    backup.write_zip(path)
    token = auth.issue_export_token(conn, account["id"])
    auth.mark_claimed(conn, account["id"])
    return FileResponse(
        path,
        filename="coffeebar-backup.zip",
        media_type="application/zip",
        headers={"X-Export-Token": token, "Access-Control-Expose-Headers": "X-Export-Token"},
        background=BackgroundTask(lambda p=path: p.unlink(missing_ok=True)),
    )

