"""샘플 데이터 생성기 — 화면과 통계를 빈 화면이 아닌 상태로 확인하려고 쓴다.

  .venv\\Scripts\\python.exe scripts\\seed.py          # 비어 있을 때만 채움
  .venv\\Scripts\\python.exe scripts\\seed.py --reset  # 싹 지우고 다시 채움

경계 케이스를 일부러 섞어 넣는다:
  · 총 페이지를 모르는 책
  · 마감일을 이미 넘긴 책
  · 세션 없이 완독으로만 등록된 (과거에 읽은) 책
  · 진도를 되돌려 음수가 된 기록
  · 기록이 하루 비어 연속이 끊긴 구간
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import cursor, init_db  # noqa: E402

TODAY = date.today()
random.seed(20260730)


def d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).strftime("%Y-%m-%d")


# (제목, 저자, 출판사, 카테고리, 총페이지)
DONE_BOOKS = [
    ("사피엔스", "유발 하라리", "김영사", "인문학", 636),
    ("미움받을 용기", "기시미 이치로", "인플루엔셜", "인문학", 336),
    ("아몬드", "손원평", "창비", "소설", 272),
    ("팩트풀니스", "한스 로슬링", "김영사", "사회과학", 432),
    ("코스모스", "칼 세이건", "사이언스북스", "과학", 719),
    ("불편한 편의점", "김호연", "나무옆의자", "소설", 268),
    ("돈의 심리학", "모건 하우절", "인플루엔셜", "경제경영", 416),
    ("클린 코드", "로버트 마틴", "인사이트", "컴퓨터/IT", 584),
    ("어린 왕자", "생텍쥐페리", "열린책들", "소설", 136),
    ("총, 균, 쇠", "재레드 다이아몬드", "문학사상", "인문학", 750),
    ("일의 격", "신수정", "턴어라운드", "자기계발", 340),
    ("이기적 유전자", "리처드 도킨스", "을유문화사", "과학", 632),
]

READING_BOOKS = [
    # (제목, 저자, 출판사, 카테고리, 총페이지, 현재쪽, 시작일오프셋, 마감일오프셋)
    ("호모 데우스", "유발 하라리", "김영사", "인문학", 636, 412, -26, 21),
    ("공정하다는 착각", "마이클 샌델", "와이즈베리", "사회과학", 420, 96, -9, -3),
    ("프로젝트 헤일메리", "앤디 위어", "알에이치코리아", "소설", 604, 180, -14, None),
    # 총 페이지를 모르는 책 — 진도율/마감 계산이 깨지지 않는지 보려고 일부러 남겨 둔다.
    ("빌린 책, 산 책, 버린 책", "장정일", "마티", "에세이", None, 88, -5, None),
]

WISHLIST = [
    ("숨결이 바람 될 때", "폴 칼라니티", "흐름출판", "에세이", 280),
    ("나는 왜 이 일을 하는가", "사이먼 시넥", "타임비즈", "자기계발", 320),
    ("모순", "양귀자", "쓰다", "소설", 300),
]

PAUSED = [("자본론", "칼 마르크스", "비봉출판사", "사회과학", 1088, 140)]

MEMOS = {
    "사피엔스": "인지혁명 파트가 제일 좋았다. 3부는 조금 늘어짐.",
    "아몬드": "짧은데 오래 남는다.",
    "클린 코드": "함수 길이 규칙은 실무에서 반쯤만 지키는 중.",
    "호모 데우스": "데이터교 이야기부터 속도가 붙는다.",
}


def wipe(conn):
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM books")
    conn.execute("DELETE FROM goals")
    print("기존 데이터를 지웠습니다.")


def add_book(conn, **kw) -> int:
    cols = list(kw) + ["created_at", "updated_at"]
    now = TODAY.strftime("%Y-%m-%d") + "T09:00:00"
    vals = list(kw.values()) + [now, now]
    return conn.execute(
        f"INSERT INTO books ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        vals,
    ).lastrowid


def add_session(conn, book_id, day, start, end, minutes=None, note=None):
    conn.execute(
        "INSERT INTO sessions(book_id, log_date, start_page, end_page, pages, minutes, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (book_id, day, start, end, end - start, minutes, note),
    )


def seed(conn):
    # ── 목표 ──────────────────────────────────────────────
    conn.execute(
        "INSERT INTO goals(kind, period, target, active) VALUES (?, ?, ?, 1)",
        ("yearly_books", str(TODAY.year), 24),
    )
    conn.execute(
        "INSERT INTO goals(kind, period, target, active) VALUES (?, NULL, ?, 1)",
        ("daily_pages", 30),
    )

    # ── 완독한 책 ─────────────────────────────────────────
    # 올해 골고루 흩어 놓는다. 뒤쪽 두 권은 세션 없이 완독으로만 등록해
    # "과거에 읽은 책" 경로를 만든다.
    finished_offsets = [-198, -175, -150, -128, -110, -88, -70, -52, -35, -20, -9, -2]
    for (title, author, pub, cat, pages), off in zip(DONE_BOOKS, finished_offsets):
        started = off - random.randint(6, 30)
        book_id = add_book(
            conn,
            title=title, author=author, publisher=pub, category=cat,
            total_pages=pages, current_page=pages, status="done",
            rating=random.choice([3, 4, 4, 5, 5]),
            memo=MEMOS.get(title),
            started_on=d(started), finished_on=d(off),
        )
        if title in ("어린 왕자", "이기적 유전자"):
            continue  # 세션 없는 완독 기록

        # 시작일~완독일 사이에 드문드문 읽은 흔적
        page = 0
        day = started
        while day < off and page < pages:
            day += random.randint(1, 3)
            if day >= off:
                break
            chunk = min(pages - page, random.randint(18, 55))
            add_session(conn, book_id, d(day), page, page + chunk,
                        random.choice([None, 20, 25, 30, 40, 45]))
            page += chunk
        if page < pages:
            add_session(conn, book_id, d(off), page, pages, 35)

    # ── 읽는 중 ───────────────────────────────────────────
    for title, author, pub, cat, pages, cur, start_off, due_off in READING_BOOKS:
        book_id = add_book(
            conn,
            title=title, author=author, publisher=pub, category=cat,
            total_pages=pages, current_page=cur, status="reading",
            memo=MEMOS.get(title),
            started_on=d(start_off),
            due_date=d(due_off) if due_off is not None else None,
        )
        page, day = 0, start_off
        while page < cur:
            day += random.randint(1, 2)
            if day > 0:
                break
            chunk = min(cur - page, random.randint(15, 45))
            add_session(conn, book_id, d(day), page, page + chunk,
                        random.choice([None, 20, 30, 35]))
            page += chunk
        if page < cur:
            add_session(conn, book_id, d(0), page, cur, 25)

        # 잘못 눌러 되돌린 기록 하나 — 음수 페이지 처리 확인용
        if title == "프로젝트 헤일메리":
            add_session(conn, book_id, d(-4), 195, 180, None, "잘못 눌러서 되돌림")

    # ── 읽고싶은 책 ───────────────────────────────────────
    for title, author, pub, cat, pages in WISHLIST:
        add_book(conn, title=title, author=author, publisher=pub, category=cat,
                 total_pages=pages, current_page=0, status="wishlist")

    # ── 중단 ──────────────────────────────────────────────
    for title, author, pub, cat, pages, cur in PAUSED:
        book_id = add_book(conn, title=title, author=author, publisher=pub,
                           category=cat, total_pages=pages, current_page=cur,
                           status="paused", started_on=d(-120))
        add_session(conn, book_id, d(-120), 0, cur, 90)

    n_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    n_sess = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    print(f"샘플 데이터 생성 완료: 책 {n_books}권 · 날짜별 기록 {n_sess}건")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="기존 데이터를 지우고 다시 채움")
    args = ap.parse_args()

    init_db()
    with cursor() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        if existing and not args.reset:
            print(f"이미 책 {existing}권이 있습니다. 덮어쓰려면 --reset 을 붙이세요.")
            return
        if args.reset:
            wipe(conn)
        seed(conn)


if __name__ == "__main__":
    main()
