"""통계 API. 차트는 이 JSON 을 받아서 브라우저에서 SVG 로 그린다."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..db import get_db
from ..services import goals as goals_svc
from ..services import stats as stats_svc
from ..util import today

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
def summary(year: int | None = None, db: sqlite3.Connection = Depends(get_db)):
    y = year or today().year
    return {
        "year": y,
        "years": stats_svc.available_years(db),
        "this_year": stats_svc.summary(db, y),
        "all_time": stats_svc.summary(db, None),
        "yearly_goal": goals_svc.yearly_progress(db, y),
        "streak": goals_svc.streak(db),
    }


@router.get("/charts")
def charts(year: int | None = None, db: sqlite3.Connection = Depends(get_db)):
    y = year or today().year
    return {
        "year": y,
        "monthly": stats_svc.monthly(db, y),
        "categories": stats_svc.by_category(db, y),
        "heatmap": stats_svc.heatmap(db, y),
        "authors": stats_svc.top_authors(db, y),
        "publishers": stats_svc.top_publishers(db, y),
        "ratings": stats_svc.rating_distribution(db, y),
    }


@router.get("/daily")
def daily(days: int = 30, db: sqlite3.Connection = Depends(get_db)):
    return {"series": stats_svc.daily_series(db, max(7, min(days, 365)))}
