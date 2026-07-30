"""책 조회/생성/수정. 화면에서 바로 쓸 수 있게 파생값을 붙여 돌려준다."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from ..schemas import STATUS_LABELS, BookIn, BookUpdate
from ..util import to_date, today, today_str

SORTS = {
    "recent": "updated_at DESC",
    "title": "title COLLATE NOCASE ASC",
    "author": "author COLLATE NOCASE ASC",
    "rating": "rating DESC NULLS LAST, updated_at DESC",
    "finished": "finished_on DESC NULLS LAST",
    "progress": "CAST(current_page AS REAL) / NULLIF(total_pages, 0) DESC NULLS LAST",
}

_EDITABLE = (
    "title", "author", "publisher", "isbn13", "cover_url", "category",
    "total_pages", "status", "rating", "memo", "started_on", "finished_on",
    "due_date",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def decorate(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    """진도율·남은 페이지·마감 계산처럼 화면마다 반복되는 값을 미리 붙인다."""
    if row is None:
        return None
    b = dict(row)
    total = b.get("total_pages") or 0
    cur = b.get("current_page") or 0

    b["status_label"] = STATUS_LABELS.get(b.get("status", ""), b.get("status", ""))
    b["has_total"] = total > 0
    if total > 0:
        pct = cur / total * 100
        b["progress_pct"] = round(min(100.0, max(0.0, pct)), 1)
        b["pages_left"] = max(0, total - cur)
    else:
        # 총 페이지를 모르는 책. 진도바를 그리지 않고 "412p 읽음"만 보여준다.
        b["progress_pct"] = None
        b["pages_left"] = None

    due = to_date(b.get("due_date"))
    b["due_days_left"] = (due - today()).days if due else None
    b["due_overdue"] = bool(due and b["due_days_left"] < 0 and b.get("status") != "done")

    if due and b["pages_left"] is not None and b.get("status") != "done":
        days = max(1, b["due_days_left"]) if b["due_days_left"] > 0 else 1
        b["due_pages_per_day"] = -(-b["pages_left"] // days)  # 올림
    else:
        b["due_pages_per_day"] = None

    return b


def list_books(
    conn: sqlite3.Connection,
    status: str | None = None,
    q: str | None = None,
    sort: str = "recent",
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM books"
    where, params = [], []
    if status and status != "all":
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("(title LIKE ? OR author LIKE ? OR publisher LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + SORTS.get(sort, SORTS["recent"])
    return [decorate(r) for r in conn.execute(sql, params).fetchall()]


def get_book(conn: sqlite3.Connection, book_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    return decorate(row)


def find_by_isbn(conn: sqlite3.Connection, isbn13: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM books WHERE isbn13 = ?", (isbn13,)).fetchone()
    return decorate(row)


def create_book(conn: sqlite3.Connection, data: BookIn) -> int:
    payload = data.model_dump()

    # 읽는 중으로 바로 등록하면 시작일을 오늘로 채워 준다.
    if payload["status"] in ("reading", "done") and not payload["started_on"]:
        payload["started_on"] = today_str()
    if payload["status"] == "done":
        if not payload["finished_on"]:
            payload["finished_on"] = today_str()
        if payload["total_pages"]:
            payload["current_page"] = payload["total_pages"]

    now = _now()
    cols = list(payload.keys()) + ["created_at", "updated_at"]
    vals = list(payload.values()) + [now, now]
    sql = (
        f"INSERT INTO books ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})"
    )
    return conn.execute(sql, vals).lastrowid


def update_book(
    conn: sqlite3.Connection, book_id: int, data: BookUpdate
) -> dict[str, Any] | None:
    fields = data.model_dump(exclude_unset=True)
    fields = {k: v for k, v in fields.items() if k in _EDITABLE}
    if not fields:
        return get_book(conn, book_id)

    current = conn.execute(
        "SELECT * FROM books WHERE id = ?", (book_id,)
    ).fetchone()
    if current is None:
        return None

    new_status = fields.get("status")
    if new_status == "done":
        if "finished_on" not in fields and not current["finished_on"]:
            fields["finished_on"] = today_str()
        total = fields.get("total_pages", current["total_pages"])
        if total:
            fields["current_page"] = total
    elif new_status == "reading":
        if "started_on" not in fields and not current["started_on"]:
            fields["started_on"] = today_str()
        # 완독 → 다시 읽는 중으로 되돌리면 완독일을 지운다.
        if current["status"] == "done" and "finished_on" not in fields:
            fields["finished_on"] = None

    fields["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE books SET {sets} WHERE id = ?", [*fields.values(), book_id]
    )
    return get_book(conn, book_id)


def touch(conn: sqlite3.Connection, book_id: int) -> None:
    conn.execute("UPDATE books SET updated_at = ? WHERE id = ?", (_now(), book_id))


def delete_book(conn: sqlite3.Connection, book_id: int) -> bool:
    cur = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    return cur.rowcount > 0


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM books GROUP BY status"
    ).fetchall()
    counts = {k: 0 for k in STATUS_LABELS}
    for r in rows:
        counts[r["status"]] = r["n"]
    counts["all"] = sum(counts.values())
    return counts


def categories(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT category FROM books "
        "WHERE category IS NOT NULL AND category <> '' ORDER BY category"
    ).fetchall()
    return [r["category"] for r in rows]
