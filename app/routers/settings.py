"""설정 · CSV 내보내기 · 백업."""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import aladin, config
from ..db import connect, get_db
from ..paths import BACKUP_DIR, DB_PATH

router = APIRouter(prefix="/api", tags=["settings"])

BOOK_COLUMNS = [
    "id", "title", "author", "publisher", "isbn13", "category",
    "total_pages", "current_page", "status", "rating", "memo",
    "started_on", "finished_on", "due_date", "created_at", "updated_at",
]
SESSION_COLUMNS = [
    "id", "book_id", "title", "log_date", "start_page", "end_page",
    "pages", "minutes", "note",
]


class SettingsIn(BaseModel):
    aladin_ttb_key: str | None = None


@router.get("/settings")
def get_settings():
    key = config.get("aladin_ttb_key") or ""
    return {
        # 키 전체를 화면에 다시 뿌리지 않는다. 설정됐는지와 끝 4자리만.
        "aladin_configured": bool(key.strip()),
        "aladin_key_hint": f"…{key[-4:]}" if len(key) > 4 else "",
    }


@router.put("/settings")
def put_settings(data: SettingsIn):
    updates = {}
    if data.aladin_ttb_key is not None:
        updates["aladin_ttb_key"] = data.aladin_ttb_key.strip()
    if updates:
        config.save(updates)
    return get_settings()


def _csv_response(rows, columns, filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(dict(r))
    # 엑셀이 한글을 깨뜨리지 않도록 BOM 을 붙인다.
    payload = "﻿" + buf.getvalue()
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/books.csv")
def export_books(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM books ORDER BY id").fetchall()
    stamp = datetime.now().strftime("%Y%m%d")
    return _csv_response(rows, BOOK_COLUMNS, f"books-{stamp}.csv")


@router.get("/export/sessions.csv")
def export_sessions(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute(
        "SELECT s.*, b.title FROM sessions s JOIN books b ON b.id = s.book_id "
        "ORDER BY s.log_date, s.id"
    ).fetchall()
    stamp = datetime.now().strftime("%Y%m%d")
    return _csv_response(rows, SESSION_COLUMNS, f"sessions-{stamp}.csv")


@router.post("/backup")
def backup():
    """sqlite 백업 API 로 안전하게 복사한다(WAL 이라 파일 단순 복사는 위험)."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"reading-{stamp}.db"

    src = connect()
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    return {
        "ok": True,
        "path": str(target),
        "size_kb": round(target.stat().st_size / 1024, 1),
        "source": str(DB_PATH),
    }


@router.get("/aladin/status")
def aladin_status():
    return {"configured": aladin.is_configured()}
