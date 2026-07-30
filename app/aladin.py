"""알라딘 OpenAPI 클라이언트.

TTB키가 없거나, 알라딘이 죽었거나, 그 책의 페이지 수가 등록돼 있지 않아도
앱은 그대로 돌아가야 한다. 여기서 나가는 모든 실패는 AladinError 로 통일하고
호출부는 조용히 수동 입력 폼으로 넘긴다.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from . import config

SEARCH_URL = "http://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
LOOKUP_URL = "http://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
VERSION = "20131101"
TIMEOUT = 8.0


class AladinError(Exception):
    """사용자에게 그대로 보여줄 수 있는 메시지를 담는다."""


class AladinNotConfigured(AladinError):
    pass


def is_configured() -> bool:
    return bool(config.get("aladin_ttb_key"))


def _key() -> str:
    key = config.get("aladin_ttb_key") or ""
    if not key.strip():
        raise AladinNotConfigured(
            "알라딘 TTB키가 설정돼 있지 않습니다. 설정 화면에서 등록하거나 "
            "책 정보를 직접 입력해 주세요."
        )
    return key.strip()


def _parse(text: str) -> dict[str, Any]:
    """알라딘 응답은 JSON 이지만 끝에 세미콜론이 붙거나 제어문자가 섞여 온다."""
    body = text.strip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        return json.loads(body, strict=False)
    except json.JSONDecodeError as exc:
        raise AladinError("알라딘 응답을 해석하지 못했습니다.") from exc


def _category(category_name: str | None) -> str | None:
    """'국내도서>인문학>교양 인문학' → '인문학'."""
    if not category_name:
        return None
    parts = [p.strip() for p in category_name.split(">") if p.strip()]
    if len(parts) >= 2:
        return parts[1]
    return parts[0] if parts else None


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    sub = item.get("subInfo") or {}
    page = sub.get("itemPage")
    try:
        page = int(page) if page else None
        if page is not None and page <= 0:
            page = None
    except (TypeError, ValueError):
        page = None

    cover = item.get("cover") or None
    if cover:
        # coversum(작은 표지) 대신 조금 큰 이미지를 쓴다.
        cover = cover.replace("/coversum/", "/cover200/")

    return {
        "title": (item.get("title") or "").strip(),
        "author": (item.get("author") or "").strip() or None,
        "publisher": (item.get("publisher") or "").strip() or None,
        "isbn13": (item.get("isbn13") or item.get("isbn") or "").strip() or None,
        "cover_url": cover,
        "category": _category(item.get("categoryName")),
        "total_pages": page,
        "pub_date": (item.get("pubDate") or "").strip() or None,
        "description": (item.get("description") or "").strip() or None,
    }


async def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise AladinError("알라딘 응답이 너무 느립니다. 직접 입력해 주세요.") from exc
    except httpx.HTTPError as exc:
        raise AladinError(
            "알라딘에 연결하지 못했습니다. 인터넷 연결이나 TTB키를 확인해 주세요."
        ) from exc

    data = _parse(resp.text)
    if data.get("errorCode"):
        raise AladinError(
            f"알라딘 오류: {data.get('errorMessage') or data['errorCode']}"
        )
    return data


async def search(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """제목/저자 키워드 검색. 목록에는 페이지 수가 없으므로 None 으로 온다."""
    query = (query or "").strip()
    if not query:
        return []

    data = await _get(
        SEARCH_URL,
        {
            "ttbkey": _key(),
            "Query": query,
            "QueryType": "Keyword",
            "MaxResults": max(1, min(max_results, 30)),
            "start": 1,
            "SearchTarget": "Book",
            "Cover": "MidBig",
            "output": "js",
            "Version": VERSION,
        },
    )
    return [_normalize(i) for i in data.get("item", [])]


async def lookup(isbn13: str) -> dict[str, Any] | None:
    """ISBN 상세 조회. OptResult=packing 을 붙여야 subInfo.itemPage(총 페이지)가 온다.

    알라딘에 페이지 수가 등록돼 있지 않은 책도 많다. 그때는 total_pages 가
    None 으로 돌아오고, 화면에서 직접 입력하도록 안내한다.
    """
    isbn13 = "".join(ch for ch in (isbn13 or "") if ch.isdigit() or ch.upper() == "X")
    if not isbn13:
        return None

    data = await _get(
        LOOKUP_URL,
        {
            "ttbkey": _key(),
            "itemIdType": "ISBN13" if len(isbn13) == 13 else "ISBN",
            "ItemId": isbn13,
            "Cover": "MidBig",
            "OptResult": "packing",
            "output": "js",
            "Version": VERSION,
        },
    )
    items = data.get("item") or []
    return _normalize(items[0]) if items else None


async def search_with_pages(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """검색 결과 + 각 항목의 페이지 수까지 채워서 돌려준다.

    검색 API 는 페이지 수를 안 주기 때문에 결과마다 상세 조회를 한 번 더 한다.
    호출 수가 결과 개수만큼 늘어나므로 기본 개수를 작게 잡았다.
    하나가 실패해도 나머지는 그대로 살린다.
    """
    import asyncio

    items = await search(query, max_results)

    async def fill(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("total_pages") or not item.get("isbn13"):
            return item
        try:
            detail = await lookup(item["isbn13"])
        except AladinError:
            return item
        if detail and detail.get("total_pages"):
            item["total_pages"] = detail["total_pages"]
        return item

    return list(await asyncio.gather(*(fill(i) for i in items)))
