"""책 · 진도 · 세션 API."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..schemas import BookIn, BookUpdate, FinishIn, ProgressIn, SessionUpdate
from ..services import books as books_svc
from ..services import goals as goals_svc
from ..services import progress as progress_svc
from ..services import stats as stats_svc

router = APIRouter(prefix="/api", tags=["books"])


@router.get("/books")
def list_books(
    status: str | None = None,
    q: str | None = None,
    sort: str = "recent",
    db: sqlite3.Connection = Depends(get_db),
):
    return {
        "books": books_svc.list_books(db, status=status, q=q, sort=sort),
        "counts": books_svc.status_counts(db),
    }


@router.post("/books", status_code=201)
def create_book(data: BookIn, db: sqlite3.Connection = Depends(get_db)):
    if data.isbn13:
        existing = books_svc.find_by_isbn(db, data.isbn13)
        if existing:
            raise HTTPException(
                409,
                detail={
                    "message": f"이미 서재에 있는 책입니다: {existing['title']}",
                    "book_id": existing["id"],
                },
            )
    try:
        book_id = books_svc.create_book(db, data)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, detail={"message": f"저장하지 못했습니다: {exc}"})
    return books_svc.get_book(db, book_id)


@router.get("/books/{book_id}")
def get_book(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    book = books_svc.get_book(db, book_id)
    if book is None:
        raise HTTPException(404, "책을 찾을 수 없습니다.")
    book["sessions"] = progress_svc.list_sessions(db, book_id)
    book["series"] = stats_svc.book_progress_series(db, book_id)
    book["outlook"] = goals_svc.deadline_outlook(db, book)
    return book


@router.patch("/books/{book_id}")
def update_book(
    book_id: int, data: BookUpdate, db: sqlite3.Connection = Depends(get_db)
):
    try:
        book = books_svc.update_book(db, book_id, data)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "같은 ISBN 의 책이 이미 있습니다.")
    if book is None:
        raise HTTPException(404, "책을 찾을 수 없습니다.")
    return book


@router.delete("/books/{book_id}")
def delete_book(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not books_svc.delete_book(db, book_id):
        raise HTTPException(404, "책을 찾을 수 없습니다.")
    return {"ok": True}


@router.patch("/books/{book_id}/progress")
def update_progress(
    book_id: int, data: ProgressIn, db: sqlite3.Connection = Depends(get_db)
):
    book = progress_svc.update_progress(db, book_id, data)
    if book is None:
        raise HTTPException(404, "책을 찾을 수 없습니다.")
    book["daily"] = goals_svc.daily_progress(db)
    book["streak"] = goals_svc.streak(db)
    book["outlook"] = goals_svc.deadline_outlook(db, book)
    return book


@router.post("/books/{book_id}/finish")
def finish_book(
    book_id: int, data: FinishIn, db: sqlite3.Connection = Depends(get_db)
):
    book = progress_svc.finish_book(
        db, book_id, rating=data.rating, finished_on=data.finished_on, memo=data.memo
    )
    if book is None:
        raise HTTPException(404, "책을 찾을 수 없습니다.")
    book["yearly"] = goals_svc.yearly_progress(db)
    return book


@router.get("/books/{book_id}/sessions")
def book_sessions(book_id: int, db: sqlite3.Connection = Depends(get_db)):
    return {"sessions": progress_svc.list_sessions(db, book_id)}


@router.get("/sessions")
def recent_sessions(
    limit: int = Query(default=15, ge=1, le=200),
    db: sqlite3.Connection = Depends(get_db),
):
    return {"sessions": progress_svc.list_sessions(db, limit=limit)}


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: int, data: SessionUpdate, db: sqlite3.Connection = Depends(get_db)
):
    session = progress_svc.update_session(db, session_id, data)
    if session is None:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return session


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: sqlite3.Connection = Depends(get_db)):
    if not progress_svc.delete_session(db, session_id):
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    return {"ok": True}
