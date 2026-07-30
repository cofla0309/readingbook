"""목표 3종의 진척·페이스 계산.

  ① 연간 권수   ② 일일 페이지/시간   ③ 책별 마감일
"""
from __future__ import annotations

import sqlite3
from calendar import isleap
from datetime import date, timedelta
from typing import Any

from ..schemas import GoalIn
from ..util import today, today_str, year_bounds

KINDS = ("yearly_books", "daily_pages", "daily_minutes")


# ── 목표 저장/조회 ────────────────────────────────────────────────

def get_goals(conn: sqlite3.Connection, year: int | None = None) -> dict[str, Any]:
    """kind -> 목표 행. 연간 목표는 해당 연도 것만 집어 온다."""
    year = year or today().year
    out: dict[str, Any] = {}
    rows = conn.execute("SELECT * FROM goals WHERE active = 1").fetchall()
    for r in rows:
        if r["kind"] == "yearly_books":
            if r["period"] == str(year):
                out["yearly_books"] = dict(r)
        else:
            out[r["kind"]] = dict(r)
    return out


def set_goal(conn: sqlite3.Connection, data: GoalIn) -> None:
    period = data.period
    if data.kind == "yearly_books" and not period:
        period = str(today().year)
    if data.kind != "yearly_books":
        period = None

    if period is None:
        conn.execute(
            "INSERT INTO goals(kind, period, target, active) VALUES(?, NULL, ?, ?) "
            "ON CONFLICT(kind) WHERE period IS NULL "
            "DO UPDATE SET target = excluded.target, active = excluded.active",
            (data.kind, data.target, int(data.active)),
        )
    else:
        conn.execute(
            "INSERT INTO goals(kind, period, target, active) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(kind, period) "
            "DO UPDATE SET target = excluded.target, active = excluded.active",
            (data.kind, period, data.target, int(data.active)),
        )


def clear_goal(conn: sqlite3.Connection, kind: str, period: str | None = None) -> None:
    if kind == "yearly_books":
        conn.execute(
            "DELETE FROM goals WHERE kind = ? AND period = ?",
            (kind, period or str(today().year)),
        )
    else:
        conn.execute("DELETE FROM goals WHERE kind = ? AND period IS NULL", (kind,))


# ── ① 연간 권수 ──────────────────────────────────────────────────

def yearly_progress(
    conn: sqlite3.Connection, year: int | None = None
) -> dict[str, Any]:
    year = year or today().year
    start, end = year_bounds(year)

    done = conn.execute(
        "SELECT COUNT(*) AS n FROM books "
        "WHERE status = 'done' AND finished_on BETWEEN ? AND ?",
        (start, end),
    ).fetchone()["n"]

    goal = get_goals(conn, year).get("yearly_books")
    target = goal["target"] if goal else None

    days_total = 366 if isleap(year) else 365
    if year == today().year:
        days_elapsed = (today() - date(year, 1, 1)).days + 1
    elif year < today().year:
        days_elapsed = days_total
    else:
        days_elapsed = 0

    # 지금 페이스를 연말까지 그대로 이었을 때의 예상 권수.
    projected = round(done / days_elapsed * days_total) if days_elapsed else 0

    out: dict[str, Any] = {
        "year": year,
        "done": done,
        "target": target,
        "days_elapsed": days_elapsed,
        "days_total": days_total,
        "days_left": max(0, days_total - days_elapsed),
        "projected": projected,
    }
    if target:
        out["pct"] = round(min(100.0, done / target * 100), 1)
        out["remaining"] = max(0, target - done)
        # 목표 대비 지금쯤 몇 권이어야 하는지
        out["expected_by_now"] = round(target * days_elapsed / days_total, 1)
        out["ahead"] = round(done - out["expected_by_now"], 1)
        out["on_track"] = done >= out["expected_by_now"]
        if out["remaining"] and out["days_left"]:
            out["days_per_book"] = round(out["days_left"] / out["remaining"], 1)
        else:
            out["days_per_book"] = None
    else:
        out["pct"] = None
    return out


# ── ② 일일 페이지/시간 ───────────────────────────────────────────

def daily_totals(
    conn: sqlite3.Connection, start: str, end: str
) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        "SELECT log_date, SUM(pages) AS pages, SUM(COALESCE(minutes, 0)) AS minutes "
        "FROM sessions WHERE log_date BETWEEN ? AND ? GROUP BY log_date",
        (start, end),
    ).fetchall()
    return {
        r["log_date"]: {"pages": r["pages"] or 0, "minutes": r["minutes"] or 0}
        for r in rows
    }


def daily_progress(
    conn: sqlite3.Connection, day: str | None = None
) -> dict[str, Any]:
    day = day or today_str()
    row = conn.execute(
        "SELECT SUM(pages) AS pages, SUM(COALESCE(minutes, 0)) AS minutes, "
        "COUNT(DISTINCT book_id) AS books FROM sessions WHERE log_date = ?",
        (day,),
    ).fetchone()

    goals = get_goals(conn)
    pages = row["pages"] or 0
    minutes = row["minutes"] or 0

    out: dict[str, Any] = {
        "date": day,
        "pages": pages,
        "minutes": minutes,
        "books": row["books"] or 0,
        "pages_target": None,
        "minutes_target": None,
        "pages_pct": None,
        "minutes_pct": None,
        "met": None,
    }
    met_flags = []
    if "daily_pages" in goals:
        t = goals["daily_pages"]["target"]
        out["pages_target"] = t
        out["pages_pct"] = round(min(100.0, max(0, pages) / t * 100), 1)
        met_flags.append(pages >= t)
    if "daily_minutes" in goals:
        t = goals["daily_minutes"]["target"]
        out["minutes_target"] = t
        out["minutes_pct"] = round(min(100.0, minutes / t * 100), 1)
        met_flags.append(minutes >= t)
    if met_flags:
        out["met"] = any(met_flags)
    return out


def _day_meets(totals: dict[str, int], goals: dict[str, Any]) -> bool:
    """일일 목표가 있으면 '목표를 채운 날', 없으면 '읽은 날'을 인정한다."""
    checks = []
    if "daily_pages" in goals:
        checks.append(totals["pages"] >= goals["daily_pages"]["target"])
    if "daily_minutes" in goals:
        checks.append(totals["minutes"] >= goals["daily_minutes"]["target"])
    if checks:
        return any(checks)
    return totals["pages"] > 0 or totals["minutes"] > 0


def streak(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT log_date, SUM(pages) AS pages, SUM(COALESCE(minutes, 0)) AS minutes "
        "FROM sessions GROUP BY log_date ORDER BY log_date"
    ).fetchall()
    if not rows:
        return {"current": 0, "longest": 0, "last_date": None}

    goals = get_goals(conn)
    met_days = {
        r["log_date"]
        for r in rows
        if _day_meets(
            {"pages": r["pages"] or 0, "minutes": r["minutes"] or 0}, goals
        )
    }
    if not met_days:
        return {"current": 0, "longest": 0, "last_date": None}

    # 현재 연속: 오늘부터 거슬러 올라간다. 오늘은 아직 안 끝났으므로
    # 오늘이 비어 있어도 끊긴 것으로 보지 않고 어제부터 센다.
    cur_day = today()
    if cur_day.strftime("%Y-%m-%d") not in met_days:
        cur_day -= timedelta(days=1)
    current = 0
    while cur_day.strftime("%Y-%m-%d") in met_days:
        current += 1
        cur_day -= timedelta(days=1)

    # 최장 연속
    ordered = sorted(met_days)
    longest = run = 1
    prev = date.fromisoformat(ordered[0])
    for s in ordered[1:]:
        d = date.fromisoformat(s)
        run = run + 1 if (d - prev).days == 1 else 1
        longest = max(longest, run)
        prev = d

    return {"current": current, "longest": longest, "last_date": ordered[-1]}


# ── ③ 책별 마감일 ────────────────────────────────────────────────

def recent_speed(
    conn: sqlite3.Connection, book_id: int, window_days: int = 14
) -> float:
    """최근 window_days 동안의 하루 평균 페이지(그 책 기준)."""
    since = (today() - timedelta(days=window_days - 1)).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT SUM(pages) AS pages FROM sessions "
        "WHERE book_id = ? AND log_date >= ?",
        (book_id, since),
    ).fetchone()
    pages = row["pages"] or 0
    return max(0.0, pages / window_days)


def deadline_outlook(conn: sqlite3.Connection, book: dict[str, Any]) -> dict[str, Any]:
    """마감일이 있는 책의 '하루 몇 쪽 필요 / 이 속도면 언제 끝' 계산."""
    out: dict[str, Any] = {
        "needed_per_day": book.get("due_pages_per_day"),
        "days_left": book.get("due_days_left"),
        "speed": None,
        "eta": None,
        "eta_late": None,
    }
    if book.get("status") == "done" or not book.get("has_total"):
        return out

    speed = recent_speed(conn, book["id"])
    out["speed"] = round(speed, 1)
    left = book.get("pages_left") or 0
    if speed > 0 and left > 0:
        eta_days = -(-left // speed)  # 올림
        eta = today() + timedelta(days=int(eta_days))
        out["eta"] = eta.strftime("%Y-%m-%d")
        if book.get("due_date"):
            out["eta_late"] = eta.strftime("%Y-%m-%d") > book["due_date"]
    return out
