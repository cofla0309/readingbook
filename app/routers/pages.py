"""HTML 화면 5개. 데이터는 서버에서 렌더링하고, 차트용 숫자만 JSON 으로 심는다."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import aladin
from ..db import get_db
from ..paths import TEMPLATES_DIR
from ..schemas import STATUS_LABELS
from ..services import books as books_svc
from ..services import goals as goals_svc
from ..services import progress as progress_svc
from ..services import stats as stats_svc
from ..util import today, today_str

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _base(request: Request, active: str) -> dict:
    return {
        "request": request,
        "active": active,
        "today": today_str(),
        "status_labels": STATUS_LABELS,
        "aladin_ready": aladin.is_configured(),
    }


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: sqlite3.Connection = Depends(get_db)):
    reading = books_svc.list_books(db, status="reading", sort="recent")
    for b in reading:
        b["outlook"] = goals_svc.deadline_outlook(db, b)
    # 마감이 급한 책을 위로.
    reading.sort(
        key=lambda b: (
            b["due_days_left"] if b["due_days_left"] is not None else 10_000
        )
    )

    ctx = _base(request, "dashboard")
    ctx.update(
        yearly=goals_svc.yearly_progress(db),
        daily=goals_svc.daily_progress(db),
        streak=goals_svc.streak(db),
        reading=reading,
        counts=books_svc.status_counts(db),
        recent_sessions=progress_svc.list_sessions(db, limit=8),
        week=stats_svc.daily_series(db, 14),
    )
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.get("/library", response_class=HTMLResponse)
def library(
    request: Request,
    status: str = "reading",
    q: str | None = None,
    sort: str = "recent",
    db: sqlite3.Connection = Depends(get_db),
):
    ctx = _base(request, "library")
    ctx.update(
        books=books_svc.list_books(db, status=status, q=q, sort=sort),
        counts=books_svc.status_counts(db),
        categories=books_svc.categories(db),
        filter_status=status,
        filter_q=q or "",
        filter_sort=sort,
    )
    return templates.TemplateResponse(request, "library.html", ctx)


@router.get("/books/{book_id}", response_class=HTMLResponse)
def book_detail(
    request: Request, book_id: int, db: sqlite3.Connection = Depends(get_db)
):
    book = books_svc.get_book(db, book_id)
    if book is None:
        raise HTTPException(404, "책을 찾을 수 없습니다.")

    ctx = _base(request, "library")
    ctx.update(
        book=book,
        sessions=progress_svc.list_sessions(db, book_id),
        series=stats_svc.book_progress_series(db, book_id),
        outlook=goals_svc.deadline_outlook(db, book),
        categories=books_svc.categories(db),
    )
    return templates.TemplateResponse(request, "book.html", ctx)


@router.get("/stats", response_class=HTMLResponse)
def stats_page(
    request: Request, year: int | None = None, db: sqlite3.Connection = Depends(get_db)
):
    y = year or today().year
    ctx = _base(request, "stats")
    ctx.update(
        year=y,
        years=stats_svc.available_years(db),
        this_year=stats_svc.summary(db, y),
        all_time=stats_svc.summary(db, None),
        yearly=goals_svc.yearly_progress(db, y),
        streak=goals_svc.streak(db),
        charts={
            "year": y,
            "monthly": stats_svc.monthly(db, y),
            "categories": stats_svc.by_category(db, y),
            "heatmap": stats_svc.heatmap(db, y),
            "ratings": stats_svc.rating_distribution(db, y),
            "daily": stats_svc.daily_series(db, 90),
        },
        authors=stats_svc.top_authors(db, y),
        publishers=stats_svc.top_publishers(db, y),
    )
    return templates.TemplateResponse(request, "stats.html", ctx)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: sqlite3.Connection = Depends(get_db)):
    from .settings import get_settings

    ctx = _base(request, "settings")
    ctx.update(
        settings=get_settings(),
        goals=goals_svc.get_goals(db),
        yearly=goals_svc.yearly_progress(db),
        year=today().year,
    )
    return templates.TemplateResponse(request, "settings.html", ctx)
