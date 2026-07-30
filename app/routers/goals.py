"""목표 API."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..db import get_db
from ..schemas import GoalIn
from ..services import goals as goals_svc

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("")
def get_goals(year: int | None = None, db: sqlite3.Connection = Depends(get_db)):
    return {
        "goals": goals_svc.get_goals(db, year),
        "yearly": goals_svc.yearly_progress(db, year),
        "daily": goals_svc.daily_progress(db),
        "streak": goals_svc.streak(db),
    }


@router.put("")
def put_goal(data: GoalIn, db: sqlite3.Connection = Depends(get_db)):
    goals_svc.set_goal(db, data)
    return get_goals(None, db)


@router.delete("/{kind}")
def delete_goal(
    kind: str, period: str | None = None, db: sqlite3.Connection = Depends(get_db)
):
    goals_svc.clear_goal(db, kind, period)
    return {"ok": True}
