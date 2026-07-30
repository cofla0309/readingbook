"""진도 갱신 = 세션 기록.

별도의 "오늘 독서 입력" 화면을 두지 않는 것이 이 앱의 핵심 설계다.
책 카드에서 현재 페이지를 412 → 455 로 바꾸면 여기서
`오늘 / 그 책 / +43p` 세션 행을 알아서 만들거나 갱신한다.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from ..schemas import ProgressIn, SessionUpdate
from ..util import today_str
from .books import decorate, get_book, touch


def _latest_session(conn: sqlite3.Connection, book_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM sessions WHERE book_id = ? "
        "ORDER BY log_date DESC, id DESC LIMIT 1",
        (book_id,),
    ).fetchone()


def recompute_current_page(conn: sqlite3.Connection, book_id: int) -> None:
    """세션을 고치거나 지운 뒤 책의 현재 페이지를 다시 맞춘다.

    세션이 하나도 없는 책(과거에 읽은 책을 완독으로만 등록한 경우)은
    current_page 를 건드리지 않는다. 손으로 넣은 값을 지워 버리면 안 되니까.
    """
    last = _latest_session(conn, book_id)
    if last is None:
        return
    conn.execute(
        "UPDATE books SET current_page = ? WHERE id = ?", (last["end_page"], book_id)
    )
    touch(conn, book_id)


def update_progress(
    conn: sqlite3.Connection, book_id: int, data: ProgressIn
) -> dict[str, Any] | None:
    book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if book is None:
        return None

    old_page = book["current_page"] or 0
    new_page = data.current_page
    log_date = data.log_date or today_str()
    total = book["total_pages"] or 0

    # 총 페이지를 아는 책이면 그 위를 넘어가지 않도록 자른다.
    if total:
        new_page = min(new_page, total)

    delta = new_page - old_page
    nothing_to_log = delta == 0 and not data.minutes and not data.note

    if not nothing_to_log:
        same_day = conn.execute(
            "SELECT * FROM sessions WHERE book_id = ? AND log_date = ? "
            "ORDER BY id DESC LIMIT 1",
            (book_id, log_date),
        ).fetchone()

        if same_day:
            # 하루에 여러 번 눌러도 그날 행은 하나로 유지한다.
            start = same_day["start_page"]
            minutes = same_day["minutes"]
            if data.minutes:
                minutes = (minutes or 0) + data.minutes
            note = data.note or same_day["note"]
            conn.execute(
                "UPDATE sessions SET end_page = ?, pages = ?, minutes = ?, note = ? "
                "WHERE id = ?",
                (new_page, new_page - start, minutes, note, same_day["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO sessions"
                "(book_id, log_date, start_page, end_page, pages, minutes, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book_id, log_date, old_page, new_page, delta, data.minutes, data.note),
            )

    # ── 상태 자동 전환 ────────────────────────────────────────────
    updates: dict[str, Any] = {"current_page": new_page}
    status = book["status"]

    if status in ("wishlist", "paused") and new_page > 0:
        updates["status"] = "reading"
        if not book["started_on"]:
            updates["started_on"] = log_date
    elif status == "reading" and not book["started_on"] and new_page > 0:
        updates["started_on"] = log_date
    elif status == "done" and total and new_page < total:
        # 완독 처리된 책의 진도를 되돌렸다 = 잘못 눌렀거나 다시 읽는 중.
        updates["status"] = "reading"
        updates["finished_on"] = None

    sets = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE books SET {sets} WHERE id = ?", [*updates.values(), book_id]
    )
    touch(conn, book_id)

    result = get_book(conn, book_id)
    # 다 읽었으면 완독 확인을 띄우도록 신호만 보낸다. 자동으로 끝내지 않는다.
    result["completion_suggested"] = bool(
        total and new_page >= total and result["status"] != "done"
    )
    result["logged_pages"] = delta
    return result


def finish_book(
    conn: sqlite3.Connection,
    book_id: int,
    rating: int | None = None,
    finished_on: str | None = None,
    memo: str | None = None,
) -> dict[str, Any] | None:
    book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if book is None:
        return None

    fields: dict[str, Any] = {
        "status": "done",
        "finished_on": finished_on or book["finished_on"] or today_str(),
    }
    if book["total_pages"]:
        fields["current_page"] = book["total_pages"]
    if rating is not None:
        fields["rating"] = rating
    if memo is not None:
        fields["memo"] = memo
    if not book["started_on"]:
        fields["started_on"] = fields["finished_on"]

    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE books SET {sets} WHERE id = ?", [*fields.values(), book_id])
    touch(conn, book_id)
    return get_book(conn, book_id)


# ── 세션 직접 편집 ────────────────────────────────────────────────

def list_sessions(
    conn: sqlite3.Connection, book_id: int | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT s.*, b.title, b.cover_url FROM sessions s "
        "JOIN books b ON b.id = s.book_id"
    )
    params: list[Any] = []
    if book_id is not None:
        sql += " WHERE s.book_id = ?"
        params.append(book_id)
    sql += " ORDER BY s.log_date DESC, s.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def update_session(
    conn: sqlite3.Connection, session_id: int, data: SessionUpdate
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None

    fields = data.model_dump(exclude_unset=True)
    merged = {**dict(row), **{k: v for k, v in fields.items() if v is not None or k == "note"}}
    start = int(merged["start_page"])
    end = int(merged["end_page"])

    conn.execute(
        "UPDATE sessions SET log_date = ?, start_page = ?, end_page = ?, "
        "pages = ?, minutes = ?, note = ? WHERE id = ?",
        (
            merged["log_date"], start, end, end - start,
            merged["minutes"], merged["note"], session_id,
        ),
    )
    recompute_current_page(conn, row["book_id"])
    updated = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    return dict(updated)


def delete_session(conn: sqlite3.Connection, session_id: int) -> bool:
    row = conn.execute(
        "SELECT book_id FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    recompute_current_page(conn, row["book_id"])
    return True
