"""알라딘 검색 API.

실패해도 500 을 던지지 않는다. `ok: false` 와 사람이 읽을 수 있는 이유를
같이 돌려주고, 화면은 그걸 보고 수동 입력 폼으로 넘어간다.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from .. import aladin
from ..db import get_db

router = APIRouter(prefix="/api/aladin", tags=["aladin"])


def _mark_owned(db: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """이미 서재에 있는 책은 표시해서 중복 등록을 막는다."""
    isbns = [i["isbn13"] for i in items if i.get("isbn13")]
    owned: dict[str, int] = {}
    if isbns:
        placeholders = ",".join("?" * len(isbns))
        rows = db.execute(
            f"SELECT id, isbn13 FROM books WHERE isbn13 IN ({placeholders})", isbns
        ).fetchall()
        owned = {r["isbn13"]: r["id"] for r in rows}
    for i in items:
        i["owned_book_id"] = owned.get(i.get("isbn13") or "")
    return items


@router.get("/search")
async def search(
    q: str = Query(min_length=1),
    pages: bool = Query(default=True, description="총 페이지까지 채울지"),
    limit: int = Query(default=8, ge=1, le=20),
    db: sqlite3.Connection = Depends(get_db),
):
    try:
        items = (
            await aladin.search_with_pages(q, limit)
            if pages
            else await aladin.search(q, limit)
        )
    except aladin.AladinNotConfigured as exc:
        return {"ok": False, "reason": "not_configured", "message": str(exc), "items": []}
    except aladin.AladinError as exc:
        return {"ok": False, "reason": "error", "message": str(exc), "items": []}

    return {"ok": True, "items": _mark_owned(db, items)}


@router.get("/lookup")
async def lookup(isbn: str = Query(min_length=8)):
    try:
        item = await aladin.lookup(isbn)
    except aladin.AladinNotConfigured as exc:
        return {"ok": False, "reason": "not_configured", "message": str(exc), "item": None}
    except aladin.AladinError as exc:
        return {"ok": False, "reason": "error", "message": str(exc), "item": None}

    if item is None:
        return {
            "ok": False,
            "reason": "not_found",
            "message": "알라딘에서 찾지 못했습니다. 직접 입력해 주세요.",
            "item": None,
        }
    return {"ok": True, "item": item, "needs_pages": item.get("total_pages") is None}
