"""통계 집계. 전부 순수 SQL 결과를 JSON 친화적인 dict 로 돌려준다."""
from __future__ import annotations

import sqlite3
from typing import Any

from ..util import today, year_bounds


def available_years(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT substr(finished_on, 1, 4) AS y FROM books "
        "WHERE finished_on IS NOT NULL "
        "UNION SELECT DISTINCT substr(log_date, 1, 4) FROM sessions"
    ).fetchall()
    years = {int(r["y"]) for r in rows if r["y"] and r["y"].isdigit()}
    years.add(today().year)
    return sorted(years, reverse=True)


def summary(conn: sqlite3.Connection, year: int | None = None) -> dict[str, Any]:
    """year 를 주면 그 해, 안 주면 전체 기간."""
    if year:
        start, end = year_bounds(year)
        book_where = "status = 'done' AND finished_on BETWEEN ? AND ?"
        book_params: tuple = (start, end)
        sess_where = "log_date BETWEEN ? AND ?"
        sess_params: tuple = (start, end)
    else:
        book_where = "status = 'done'"
        book_params = ()
        sess_where = "1 = 1"
        sess_params = ()

    b = conn.execute(
        f"SELECT COUNT(*) AS books, "
        f"       COALESCE(SUM(total_pages), 0) AS pages, "
        f"       AVG(rating) AS avg_rating, "
        f"       AVG(julianday(finished_on) - julianday(started_on)) AS avg_days "
        f"FROM books WHERE {book_where}",
        book_params,
    ).fetchone()

    s = conn.execute(
        f"SELECT COALESCE(SUM(pages), 0) AS pages, "
        f"       COALESCE(SUM(minutes), 0) AS minutes, "
        f"       COUNT(DISTINCT log_date) AS days "
        f"FROM sessions WHERE {sess_where}",
        sess_params,
    ).fetchone()

    days = s["days"] or 0
    return {
        "year": year,
        "books_done": b["books"] or 0,
        "pages_from_books": b["pages"] or 0,
        "avg_rating": round(b["avg_rating"], 2) if b["avg_rating"] else None,
        "avg_days_to_finish": round(b["avg_days"], 1) if b["avg_days"] else None,
        "session_pages": s["pages"] or 0,
        "session_minutes": s["minutes"] or 0,
        "reading_days": days,
        "avg_pages_per_reading_day": round(s["pages"] / days) if days else 0,
        "avg_minutes_per_reading_day": round(s["minutes"] / days) if days else 0,
    }


def monthly(conn: sqlite3.Connection, year: int) -> list[dict[str, Any]]:
    """월별 완독 권수 + 읽은 페이지. 기록이 없는 달도 0으로 채워 12개를 채운다."""
    start, end = year_bounds(year)

    books = {
        r["m"]: r["n"]
        for r in conn.execute(
            "SELECT substr(finished_on, 6, 2) AS m, COUNT(*) AS n FROM books "
            "WHERE status = 'done' AND finished_on BETWEEN ? AND ? GROUP BY m",
            (start, end),
        ).fetchall()
    }
    pages = {
        r["m"]: r["p"]
        for r in conn.execute(
            "SELECT substr(log_date, 6, 2) AS m, SUM(pages) AS p FROM sessions "
            "WHERE log_date BETWEEN ? AND ? GROUP BY m",
            (start, end),
        ).fetchall()
    }
    minutes = {
        r["m"]: r["x"]
        for r in conn.execute(
            "SELECT substr(log_date, 6, 2) AS m, SUM(COALESCE(minutes, 0)) AS x "
            "FROM sessions WHERE log_date BETWEEN ? AND ? GROUP BY m",
            (start, end),
        ).fetchall()
    }

    out = []
    for i in range(1, 13):
        key = f"{i:02d}"
        out.append(
            {
                "month": i,
                "label": f"{i}월",
                "books": books.get(key, 0),
                "pages": max(0, pages.get(key, 0) or 0),
                "minutes": minutes.get(key, 0) or 0,
            }
        )
    return out


def by_category(conn: sqlite3.Connection, year: int | None = None) -> list[dict]:
    where = "status = 'done'"
    params: list[Any] = []
    if year:
        start, end = year_bounds(year)
        where += " AND finished_on BETWEEN ? AND ?"
        params += [start, end]
    rows = conn.execute(
        f"SELECT COALESCE(NULLIF(category, ''), '미분류') AS name, "
        f"COUNT(*) AS books, COALESCE(SUM(total_pages), 0) AS pages "
        f"FROM books WHERE {where} GROUP BY name ORDER BY books DESC, name",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _top(conn: sqlite3.Connection, column: str, year: int | None, limit: int):
    where = f"status = 'done' AND {column} IS NOT NULL AND {column} <> ''"
    params: list[Any] = []
    if year:
        start, end = year_bounds(year)
        where += " AND finished_on BETWEEN ? AND ?"
        params += [start, end]
    params.append(limit)
    rows = conn.execute(
        f"SELECT {column} AS name, COUNT(*) AS books, "
        f"COALESCE(SUM(total_pages), 0) AS pages, AVG(rating) AS avg_rating "
        f"FROM books WHERE {where} GROUP BY name "
        f"ORDER BY books DESC, pages DESC LIMIT ?",
        params,
    ).fetchall()
    return [
        {
            "name": r["name"],
            "books": r["books"],
            "pages": r["pages"],
            "avg_rating": round(r["avg_rating"], 1) if r["avg_rating"] else None,
        }
        for r in rows
    ]


def top_authors(conn, year: int | None = None, limit: int = 8):
    return _top(conn, "author", year, limit)


def top_publishers(conn, year: int | None = None, limit: int = 8):
    return _top(conn, "publisher", year, limit)


def rating_distribution(conn: sqlite3.Connection, year: int | None = None):
    where = "status = 'done' AND rating IS NOT NULL"
    params: list[Any] = []
    if year:
        start, end = year_bounds(year)
        where += " AND finished_on BETWEEN ? AND ?"
        params += [start, end]
    rows = {
        r["rating"]: r["n"]
        for r in conn.execute(
            f"SELECT rating, COUNT(*) AS n FROM books WHERE {where} GROUP BY rating",
            params,
        ).fetchall()
    }
    return [{"rating": i, "books": rows.get(i, 0)} for i in range(1, 6)]


def heatmap(conn: sqlite3.Connection, year: int) -> dict[str, int]:
    """잔디용. {'2026-07-29': 43, ...} — 기록 있는 날만."""
    start, end = year_bounds(year)
    rows = conn.execute(
        "SELECT log_date, SUM(pages) AS pages FROM sessions "
        "WHERE log_date BETWEEN ? AND ? GROUP BY log_date",
        (start, end),
    ).fetchall()
    return {r["log_date"]: max(0, r["pages"] or 0) for r in rows}


def daily_series(conn: sqlite3.Connection, days: int = 30) -> list[dict[str, Any]]:
    """최근 N일 페이지/분. 안 읽은 날도 0으로 채운다."""
    from datetime import timedelta

    end = today()
    start = end - timedelta(days=days - 1)
    rows = {
        r["log_date"]: r
        for r in conn.execute(
            "SELECT log_date, SUM(pages) AS pages, "
            "SUM(COALESCE(minutes, 0)) AS minutes FROM sessions "
            "WHERE log_date BETWEEN ? AND ? GROUP BY log_date",
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()
    }
    out = []
    cur = start
    while cur <= end:
        key = cur.strftime("%Y-%m-%d")
        r = rows.get(key)
        out.append(
            {
                "date": key,
                "label": f"{cur.month}/{cur.day}",
                "pages": max(0, (r["pages"] or 0) if r else 0),
                "minutes": (r["minutes"] or 0) if r else 0,
            }
        )
        cur += timedelta(days=1)
    return out


def book_progress_series(conn: sqlite3.Connection, book_id: int) -> list[dict]:
    """책 상세의 누적 진도 선그래프."""
    rows = conn.execute(
        "SELECT log_date, end_page FROM sessions WHERE book_id = ? "
        "ORDER BY log_date, id",
        (book_id,),
    ).fetchall()
    return [{"date": r["log_date"], "page": r["end_page"]} for r in rows]
