"""날짜 헬퍼. 전부 로컬 시간 기준의 'YYYY-MM-DD' 문자열로 다룬다."""
from __future__ import annotations

from datetime import date, datetime, timedelta

ISO = "%Y-%m-%d"


def today() -> date:
    return date.today()


def today_str() -> str:
    return date.today().strftime(ISO)


def to_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value[:10], ISO).date()
    except ValueError:
        return None


def to_str(value: date | None) -> str | None:
    return value.strftime(ISO) if value else None


def days_between(a: date, b: date) -> int:
    """b - a (일수)."""
    return (b - a).days


def date_range(start: date, end: date):
    """start부터 end까지(양끝 포함) 하루씩."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"
