"""독서 기록 앱 진입점.

  py -m uvicorn app.main:app --host 0.0.0.0 --port 8765
또는 run.bat 더블클릭.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .paths import STATIC_DIR
from .routers import books, goals, lookup, pages, settings, stats

app = FastAPI(title="독서 기록", docs_url="/api/docs", redoc_url=None)

init_db()

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(books.router)
app.include_router(goals.router)
app.include_router(stats.router)
app.include_router(settings.router)
app.include_router(lookup.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "찾을 수 없습니다."}, status_code=404)
    return HTMLResponse(
        "<meta charset='utf-8'>"
        "<div style='font-family:system-ui;padding:3rem;text-align:center'>"
        "<h1>404</h1><p>없는 페이지입니다.</p>"
        "<p><a href='/'>대시보드로</a></p></div>",
        status_code=404,
    )
