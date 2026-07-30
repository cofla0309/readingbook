"""SQLite 연결과 스키마.

파일 하나(data/reading.db)에 전부 들어간다. 백업은 이 파일 복사 한 번.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .paths import DB_PATH

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  author        TEXT,
  publisher     TEXT,
  isbn13        TEXT UNIQUE,
  cover_url     TEXT,
  category      TEXT,
  total_pages   INTEGER,
  current_page  INTEGER NOT NULL DEFAULT 0,
  status        TEXT NOT NULL DEFAULT 'wishlist'
                CHECK (status IN ('wishlist','reading','done','paused')),
  rating        INTEGER CHECK (rating BETWEEN 1 AND 5),
  memo          TEXT,
  started_on    TEXT,
  finished_on   TEXT,
  due_date      TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id          INTEGER PRIMARY KEY,
  book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  log_date    TEXT NOT NULL,
  start_page  INTEGER NOT NULL,
  end_page    INTEGER NOT NULL,
  pages       INTEGER NOT NULL,
  minutes     INTEGER,
  note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(log_date);
CREATE INDEX IF NOT EXISTS idx_sessions_book ON sessions(book_id);

CREATE TABLE IF NOT EXISTS goals (
  id       INTEGER PRIMARY KEY,
  kind     TEXT NOT NULL
           CHECK (kind IN ('yearly_books','daily_pages','daily_minutes')),
  period   TEXT,
  target   INTEGER NOT NULL,
  active   INTEGER NOT NULL DEFAULT 1,
  UNIQUE(kind, period)
);

CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""

# goals.period 는 daily 목표에서 NULL 이다. SQLite 의 UNIQUE 는 NULL 을 서로
# 다른 값으로 보기 때문에 UNIQUE(kind, period) 만으로는 daily 목표가 중복 삽입된다.
# 부분 인덱스로 "period 가 NULL 인 kind 는 하나뿐"을 강제한다.
SCHEMA += """
CREATE UNIQUE INDEX IF NOT EXISTS idx_goals_daily
  ON goals(kind) WHERE period IS NULL;
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def cursor() -> Iterator[sqlite3.Connection]:
    """쓰기용. 예외 없이 빠져나오면 커밋."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI 의존성."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with cursor() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
