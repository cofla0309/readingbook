"""요청/응답 스키마."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["wishlist", "reading", "done", "paused"]
GoalKind = Literal["yearly_books", "daily_pages", "daily_minutes"]

STATUS_LABELS: dict[str, str] = {
    "reading": "읽는 중",
    "done": "완독",
    "wishlist": "읽고싶은",
    "paused": "중단",
}


def _blank_to_none(v):
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


class BookIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str | None = None
    publisher: str | None = None
    isbn13: str | None = None
    cover_url: str | None = None
    category: str | None = None
    total_pages: int | None = Field(default=None, ge=1, le=100_000)
    current_page: int = Field(default=0, ge=0)
    status: Status = "wishlist"
    rating: int | None = Field(default=None, ge=1, le=5)
    memo: str | None = None
    started_on: str | None = None
    finished_on: str | None = None
    due_date: str | None = None

    _clean = field_validator(
        "author", "publisher", "isbn13", "cover_url", "category", "memo",
        "started_on", "finished_on", "due_date", "rating", "total_pages",
        mode="before",
    )(_blank_to_none)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("제목을 입력해 주세요.")
        return v

    @field_validator("isbn13", mode="after")
    @classmethod
    def _clean_isbn(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = "".join(ch for ch in v if ch.isdigit() or ch.upper() == "X")
        return v or None


class BookUpdate(BaseModel):
    """PATCH — 보낸 필드만 바꾼다."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = None
    publisher: str | None = None
    isbn13: str | None = None
    cover_url: str | None = None
    category: str | None = None
    total_pages: int | None = Field(default=None, ge=1, le=100_000)
    status: Status | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    memo: str | None = None
    started_on: str | None = None
    finished_on: str | None = None
    due_date: str | None = None

    _clean = field_validator(
        "author", "publisher", "isbn13", "cover_url", "category", "memo",
        "started_on", "finished_on", "due_date", "rating", "total_pages",
        mode="before",
    )(_blank_to_none)


class ProgressIn(BaseModel):
    """진도 갱신 = 세션 기록. current_page 를 새 위치로 보낸다."""

    current_page: int = Field(ge=0, le=100_000)
    minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    note: str | None = None
    log_date: str | None = None  # 미지정 시 오늘

    _clean = field_validator("note", "log_date", "minutes", mode="before")(
        _blank_to_none
    )


class SessionUpdate(BaseModel):
    log_date: str | None = None
    start_page: int | None = Field(default=None, ge=0)
    end_page: int | None = Field(default=None, ge=0)
    minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    note: str | None = None

    _clean = field_validator("note", "log_date", "minutes", mode="before")(
        _blank_to_none
    )


class GoalIn(BaseModel):
    kind: GoalKind
    target: int = Field(ge=1, le=100_000)
    period: str | None = None  # yearly_books 는 '2026', daily 는 None
    active: bool = True

    _clean = field_validator("period", mode="before")(_blank_to_none)


class FinishIn(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    finished_on: str | None = None
    memo: str | None = None

    _clean = field_validator("memo", "finished_on", "rating", mode="before")(
        _blank_to_none
    )
