import httpx
import os
from typing import Optional

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DB_ID   = os.getenv("NOTION_DB_ID", "cd24d74a-2e53-4f8b-8d54-d4abeda56955")
NOTION_VERSION = "2022-06-28"

CHANNEL_LABEL = {
    "blog":       "블로그",
    "newsletter": "뉴스레터",
    "youtube":    "유튜브",
    "shortform":  "숏폼",
}

STATUS_MAP = {
    "approved":  "승인",
    "revision":  "수정 필요",
    "rejected":  "수정 필요",
    "published": "발행 완료",
}


def _headers() -> dict:
    return {
        "Authorization":  f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type":   "application/json",
    }


async def register_draft(
    draft_id:     str,
    title:        str,
    channel_type: str,
    keyword:      str,
) -> Optional[str]:
    """노션 검수 대기 큐에 초안 등록. 노션 페이지 ID 반환. NOTION_API_KEY 없으면 None."""
    if not NOTION_API_KEY:
        return None

    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "콘텐츠 제목": {
                "title": [{"text": {"content": title or f"[{channel_type}] {keyword}"}}]
            },
            "상태":     {"select": {"name": "검수 대기"}},
            "채널":     {"select": {"name": CHANNEL_LABEL.get(channel_type, channel_type)}},
            "주제 키워드": {"rich_text": [{"text": {"content": keyword or ""}}]},
            "파일명":   {"rich_text": [{"text": {"content": draft_id}}]},
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "https://api.notion.com/v1/pages",
            headers=_headers(),
            json=payload,
        )
        res.raise_for_status()
        return res.json().get("id")


async def update_status(
    notion_page_id: str,
    status:         str,
    published_url:  str = "",
    revision_memo:  str = "",
) -> None:
    """노션 페이지 상태 업데이트. 실패해도 예외 전파 안 함."""
    if not NOTION_API_KEY or not notion_page_id:
        return

    properties: dict = {
        "상태": {"select": {"name": STATUS_MAP.get(status, "검수 대기")}},
    }
    if published_url:
        properties["발행 링크"] = {"url": published_url}
    if revision_memo:
        properties["수정 메모"] = {"rich_text": [{"text": {"content": revision_memo}}]}

    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.patch(
            f"https://api.notion.com/v1/pages/{notion_page_id}",
            headers=_headers(),
            json={"properties": properties},
        )
        res.raise_for_status()
