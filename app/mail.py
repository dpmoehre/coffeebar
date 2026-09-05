"""发信。没配 SMTP 就不发，调用方把链接写进响应或日志，方便本机测。"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def configured() -> bool:
    return bool(os.environ.get("COFFEEBAR_SMTP_HOST"))


def send(to: str, subject: str, body: str) -> bool:
    host = os.environ.get("COFFEEBAR_SMTP_HOST")
    if not host:
        return False
    port = int(os.environ.get("COFFEEBAR_SMTP_PORT") or "587")
    user = os.environ.get("COFFEEBAR_SMTP_USER") or ""
    password = os.environ.get("COFFEEBAR_SMTP_PASSWORD") or ""
    sender = os.environ.get("COFFEEBAR_SMTP_FROM") or user or "coffeebar@localhost"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        if user:
            smtp.login(user, password)
        smtp.send_message(msg)
    return True
