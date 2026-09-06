"""日历与 CSV 出表。

业务日凌晨 4 点分界。汇总排除撤回；明细带撤回标记。钱读 unit_cost 快照。
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime

import sqlite3

from . import db, freshness, stats, store

_OWNER = """(
  (c.kind = 'coffee' AND EXISTS (
      SELECT 1 FROM bean_lot l JOIN bean b ON b.id = l.bean_id
      WHERE l.id = c.lot_id AND b.owner_id = ?))
  OR
  (c.kind = 'drink' AND EXISTS (
      SELECT 1 FROM bottle_lot l JOIN bottle b ON b.id = l.bottle_id
      WHERE l.id = c.bottle_lot_id AND b.owner_id = ?))
)"""

_DAY = f"date(c.at, '-{db.DAY_CUTOFF_HOURS} hours')"


def _month_span(year: int, month: int) -> tuple[str, str]:
    start = date(year, month, 1).isoformat()
    if month == 12:
        end = date(year + 1, 1, 1).isoformat()
    else:
        end = date(year, month + 1, 1).isoformat()
    return start, end


def month(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    owner_id: int,
    person_id: int | None = None,
) -> dict:
    start, end = _month_span(year, month)
    where = f"{_OWNER} AND {_DAY} >= ? AND {_DAY} < ?"
    args: list = [owner_id, owner_id, start, end]
    if person_id:
        where += " AND c.person_id = ?"
        args.append(person_id)
    from . import menu as menu_mod

    rows = conn.execute(
        f"""SELECT {_DAY} AS day,
                   SUM(CASE WHEN c.kind = 'coffee' AND c.voided_at IS NULL THEN 1 ELSE 0 END)
                       AS coffee,
                   {menu_mod.drink_cups_sql("c")}
                       AS drink,
                   COALESCE(SUM(CASE WHEN c.kind = 'coffee' AND c.voided_at IS NULL
                                     THEN c.amount_g ELSE 0 END), 0) AS beans_g,
                   COALESCE(SUM(CASE WHEN c.kind = 'drink' AND c.voided_at IS NULL
                                     THEN c.amount_ml ELSE 0 END), 0) AS drinks_ml,
                   COALESCE(SUM(CASE WHEN c.voided_at IS NULL THEN
                     (CASE c.kind WHEN 'drink' THEN c.amount_ml ELSE c.amount_g END)
                     * COALESCE(c.unit_cost, 0) ELSE 0 END), 0) AS spent
            FROM consumption_event c
            WHERE {where}
            GROUP BY day
            ORDER BY day""",
        args,
    ).fetchall()
    days = [
        {
            "date": r["day"],
            "coffee": int(r["coffee"] or 0),
            "drink": int(r["drink"] or 0),
            "beans_g": round(float(r["beans_g"] or 0), 1),
            "drinks_ml": round(float(r["drinks_ml"] or 0), 1),
            "spent": round(float(r["spent"] or 0), 2),
        }
        for r in rows
        if (r["coffee"] or 0) or (r["drink"] or 0)
    ]
    people = [
        {"id": r["id"], "name": r["name"], "active": bool(r["active"])}
        for r in conn.execute(
            "SELECT id, name, active FROM person WHERE owner_id = ? ORDER BY active DESC, name",
            (owner_id,),
        )
    ]
    return {"year": year, "month": month, "days": days, "person_id": person_id, "people": people}


def day(
    conn: sqlite3.Connection,
    day: str,
    owner_id: int,
    person_id: int | None = None,
) -> dict:
    datetime.strptime(day, "%Y-%m-%d")
    where = f"{_OWNER} AND {_DAY} = ?"
    args: list = [owner_id, owner_id, day]
    if person_id:
        where += " AND c.person_id = ?"
        args.append(person_id)
    rows = conn.execute(
        f"""SELECT c.id, c.kind, c.at, c.amount_g, c.amount_ml, c.unit_cost,
                   c.voided_at, c.as_cup, c.note, c.serve_id,
                   b.name AS bean_name, sp.name AS spirit_name, p.name AS person_name,
                   s.name AS serve_name, s.kind AS serve_kind,
                   CASE c.kind
                     WHEN 'drink' THEN (c.amount_ml * COALESCE(c.unit_cost, 0))
                     ELSE (c.amount_g * COALESCE(c.unit_cost, 0))
                   END AS cost
            FROM consumption_event c
            LEFT JOIN bean_lot l ON l.id = c.lot_id
            LEFT JOIN bean b ON b.id = l.bean_id
            LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
            LEFT JOIN bottle sp ON sp.id = bl.bottle_id
            LEFT JOIN person p ON p.id = c.person_id
            LEFT JOIN drink_serve s ON s.id = c.serve_id
            WHERE {where}
            ORDER BY c.at, c.id""",
        args,
    ).fetchall()
    events = []
    served: dict[int, dict] = {}
    for r in rows:
        if r["kind"] == "drink" and r["serve_id"]:
            sid = int(r["serve_id"])
            ev = served.get(sid)
            if not ev:
                ev = {
                    "id": f"serve:{sid}",
                    "serve_id": sid,
                    "kind": "drink",
                    "at": r["at"],
                    "name": r["serve_name"] or r["spirit_name"],
                    "person": r["person_name"],
                    "amount_g": None,
                    "amount_ml": 0.0,
                    "cost": 0.0,
                    "as_cup": True,
                    "voided": True,
                    "note": r["note"],
                    "serve_kind": r["serve_kind"],
                    "lines": [],
                }
                served[sid] = ev
                events.append(ev)
            ev["lines"].append(
                {
                    "id": r["id"],
                    "name": r["spirit_name"],
                    "amount_ml": r["amount_ml"],
                    "cost": round(float(r["cost"] or 0), 2),
                    "voided": bool(r["voided_at"]),
                }
            )
            if not r["voided_at"]:
                ev["voided"] = False
                ev["amount_ml"] = round(ev["amount_ml"] + float(r["amount_ml"] or 0), 1)
                ev["cost"] = round(ev["cost"] + float(r["cost"] or 0), 2)
            continue
        events.append(
            {
                "id": r["id"],
                "kind": r["kind"],
                "at": r["at"],
                "name": r["bean_name"] if r["kind"] == "coffee" else r["spirit_name"],
                "person": r["person_name"],
                "amount_g": r["amount_g"],
                "amount_ml": r["amount_ml"],
                "cost": round(float(r["cost"] or 0), 2),
                "as_cup": bool(r["as_cup"]),
                "voided": bool(r["voided_at"]),
                "note": r["note"],
            }
        )
    return {"date": day, "events": events}


def _csv(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _add_zip(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name)
    info.flag_bits |= 0x800
    zf.writestr(info, data)


def export_zip(conn: sqlite3.Connection, owner_id: int, period: str = "month") -> bytes:
    summary = stats.summary(conn, period, owner_id=owner_id)
    start = summary["since"]
    cons_where = _OWNER
    cons_args: list = [owner_id, owner_id]
    if start:
        cons_where += " AND c.at >= ?"
        cons_args.append(start)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        _add_zip(
            zf,
            "统计汇总.csv",
            _csv(
                ["期间", "起点", "豆克", "咖啡杯", "酒毫升", "酒杯", "酒精克", "喝掉的钱", "买进来的钱", "在库还值"],
                [
                    [
                        summary["period"],
                        summary["since"] or "全部",
                        summary["beans_g"],
                        summary["cups"],
                        summary["drinks_ml"],
                        summary["drink_cups"],
                        summary["alcohol_g"],
                        summary["spent"],
                        summary["bought"],
                        summary["on_hand"],
                    ]
                ],
            ),
        )
        _add_zip(
            zf,
            "按人.csv",
            _csv(
                ["谁", "豆克", "杯", "平均粉量", "钱"],
                [
                    [p["name"], p["beans_g"], p["cups"], p["avg_dose_g"] or "", p["spent"]]
                    for p in summary["by_person"]
                ],
            ),
        )
        _add_zip(
            zf,
            "按日汇总.csv",
            _csv(
                ["业务日", "豆克", "杯"],
                [[d["day"], d["beans_g"], d["cups"]] for d in summary["daily"]],
            ),
        )
        cons_rows = conn.execute(
            f"""SELECT {_DAY} AS day, c.at, c.kind, c.voided_at, c.as_cup,
                       b.name AS bean_name, sp.name AS spirit_name, p.name AS person_name,
                       c.amount_g, c.amount_ml, c.unit_cost, c.note,
                       CASE c.kind
                         WHEN 'drink' THEN (c.amount_ml * COALESCE(c.unit_cost, 0))
                         ELSE (c.amount_g * COALESCE(c.unit_cost, 0))
                       END AS cost
                FROM consumption_event c
                LEFT JOIN bean_lot l ON l.id = c.lot_id
                LEFT JOIN bean b ON b.id = l.bean_id
                LEFT JOIN bottle_lot bl ON bl.id = c.bottle_lot_id
                LEFT JOIN bottle sp ON sp.id = bl.bottle_id
                LEFT JOIN person p ON p.id = c.person_id
                WHERE {cons_where}
                ORDER BY c.at, c.id""",
            cons_args,
        ).fetchall()
        _add_zip(
            zf,
            "消耗明细.csv",
            _csv(
                ["业务日", "时间", "种类", "名称", "谁", "克", "毫升", "单价", "钱", "算杯", "已撤回", "备注"],
                [
                    [
                        r["day"],
                        r["at"],
                        "咖啡" if r["kind"] == "coffee" else "酒",
                        r["bean_name"] or r["spirit_name"] or "",
                        r["person_name"] or "没记",
                        r["amount_g"] if r["amount_g"] is not None else "",
                        r["amount_ml"] if r["amount_ml"] is not None else "",
                        r["unit_cost"] if r["unit_cost"] is not None else "",
                        round(float(r["cost"] or 0), 2),
                        "是" if r["as_cup"] else "否",
                        "是" if r["voided_at"] else "",
                        r["note"] or "",
                    ]
                    for r in cons_rows
                ],
            ),
        )

        beans = store.list_beans(conn, "all", owner_id=owner_id)
        _add_zip(
            zf,
            "豆库.csv",
            _csv(
                ["豆子", "产地", "烘焙", "处理法", "标签", "账面克", "在库", "袋数"],
                [
                    [
                        b["name"],
                        b.get("origin") or "",
                        b.get("roast") or "",
                        b.get("process") or "",
                        "、".join(b.get("tags") or []),
                        b.get("balance_g") if b.get("balance_g") is not None else "",
                        "在库" if b.get("in_stock") else ("待入袋" if b.get("pending") else "历史"),
                        b.get("all_lots") or 0,
                    ]
                    for b in beans
                ],
            ),
        )

        close_delta = {
            r["lot_id"]: r["delta_g"]
            for r in conn.execute(
                """SELECT e.lot_id, e.delta_g FROM stock_event e
                   JOIN bean_lot l ON l.id = e.lot_id
                   JOIN bean b ON b.id = l.bean_id
                   WHERE e.kind = 'close_lot' AND b.owner_id = ?""",
                (owner_id,),
            )
        }
        lot_rows = []
        for b in beans:
            for lot in store.list_lots(conn, b["id"]):
                leftover = close_delta.get(lot["id"])
                lot_rows.append(
                    [
                        b["name"],
                        lot.get("seq"),
                        lot.get("nominal_g") or "",
                        lot.get("measured_g") if lot.get("measured_g") is not None else "",
                        round(lot.get("usable_g") or 0, 1),
                        round(lot.get("used_g") or 0, 1),
                        round(lot.get("balance_g") or 0, 1),
                        lot.get("price") if lot.get("price") is not None else "",
                        lot.get("bought_on") or "",
                        lot.get("roasted_on") or "",
                        lot.get("opened_on") or "",
                        lot.get("closed_at") or "",
                        round(-leftover, 1) if leftover is not None else "",
                    ]
                )
        _add_zip(
            zf,
            "豆子批次.csv",
            _csv(
                ["豆子", "第几袋", "标称克", "实称克", "可用克", "已消耗", "账面克", "买入价", "购入日", "烘焙日", "开封日", "关袋", "关袋偏差"],
                lot_rows,
            ),
        )

        scores = conn.execute(
            """SELECT b.name, s.at, s.dry, s.flavor, s.aftertaste, s.acidity,
                      s.sweetness, s.body, s.balance, s.overall, s.comment,
                      s.roasted_on, s.days_after_roast, s.window_phase, s.lot_id,
                      (SELECT COUNT(*) FROM bean_lot x
                        WHERE x.bean_id = s.bean_id AND l.id IS NOT NULL
                          AND (x.created_at < l.created_at
                               OR (x.created_at = l.created_at AND x.id <= l.id))) AS lot_seq
               FROM bean_score s
               JOIN bean b ON b.id = s.bean_id
               LEFT JOIN bean_lot l ON l.id = s.lot_id
               WHERE b.owner_id = ?
               ORDER BY s.at DESC, s.id DESC""",
            (owner_id,),
        ).fetchall()
        _add_zip(
            zf,
            "杯测分数.csv",
            _csv(
                ["豆子", "时间", "第几袋", "烘焙日", "烘后天数", "阶段", "干香", "风味", "余韵", "酸质", "甜感", "醇厚度", "平衡", "整体", "备注"],
                [
                    [
                        r["name"],
                        r["at"],
                        r["lot_seq"] or "",
                        r["roasted_on"] or "",
                        r["days_after_roast"] if r["days_after_roast"] is not None else "",
                        freshness.LABELS.get(r["window_phase"] or "", r["window_phase"] or ""),
                        r["dry"] or "",
                        r["flavor"] or "",
                        r["aftertaste"] or "",
                        r["acidity"] or "",
                        r["sweetness"] or "",
                        r["body"] or "",
                        r["balance"] or "",
                        r["overall"] or "",
                        r["comment"] or "",
                    ]
                    for r in scores
                ],
            ),
        )

        from . import spirits as spirits_mod

        bottles = spirits_mod.list_spirits(conn, "all", owner_id=owner_id)
        _add_zip(
            zf,
            "酒瓶.csv",
            _csv(
                ["酒名", "大类", "风味", "酒精度", "账面毫升", "买入价"],
                [
                    [
                        b["name"],
                        b.get("kind") or "",
                        b.get("flavor") or "",
                        b.get("abv") if b.get("abv") is not None else "",
                        b.get("balance_ml") if b.get("balance_ml") is not None else "",
                        b.get("last_price") if b.get("last_price") is not None else "",
                    ]
                    for b in bottles
                ],
            ),
        )
        blot_rows = []
        for b in bottles:
            for lot in spirits_mod.list_lots(conn, b["id"]):
                blot_rows.append(
                    [
                        b["name"],
                        lot.get("nominal_ml") or "",
                        lot.get("balance_ml") if lot.get("balance_ml") is not None else "",
                        lot.get("price") if lot.get("price") is not None else "",
                        lot.get("bought_on") or "",
                        lot.get("opened_on") or "",
                        lot.get("closed_at") or "",
                    ]
                )
        _add_zip(
            zf,
            "酒瓶批次.csv",
            _csv(
                ["酒名", "标称毫升", "账面毫升", "买入价", "购入日", "开瓶日", "关瓶"],
                blot_rows,
            ),
        )

        restock = stats.restock_list(conn, owner_id=owner_id)
        _add_zip(
            zf,
            "补货清单.csv",
            _csv(
                ["豆子", "账面克", "还能几杯", "原因"],
                [
                    [r["name"], r["balance_g"], r["cups_left"], "；".join(r.get("reasons") or [])]
                    for r in restock
                ],
            ),
        )

    return out.getvalue()
