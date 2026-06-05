"""
노션 검수 대기 큐 상태 변경 감지 → 자동 발행 / DB 동기화
NOTION_API_KEY 없으면 아무것도 안 함.
"""
import asyncio
import httpx
import os
from sqlalchemy import select
from database import AsyncSessionLocal
from models import ContentDraft

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DB_ID   = os.getenv("NOTION_DB_ID", "cd24d74a-2e53-4f8b-8d54-d4abeda56955")
NOTION_VERSION = "2022-06-28"
POLL_INTERVAL  = 60  # 초


def _headers():
    return {
        "Authorization":  f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type":   "application/json",
    }


async def _query_notion_by_status(status_name: str) -> list[dict]:
    """노션 DB에서 특정 상태 페이지 목록 조회."""
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
            headers=_headers(),
            json={"filter": {"property": "상태", "select": {"equals": status_name}}},
        )
        res.raise_for_status()
        return res.json().get("results", [])


async def _get_draft_id_from_notion_page(page: dict) -> str:
    """노션 페이지의 파일명 프로퍼티에서 draft_id 추출."""
    props = page.get("properties", {})
    filename_prop = props.get("파일명", {})
    rich_text = filename_prop.get("rich_text", [])
    if rich_text:
        return rich_text[0].get("text", {}).get("content", "")
    return None


async def _process_approved():
    """노션에서 '승인' → DB가 아직 'review' 상태면 발행 트리거."""
    pages = await _query_notion_by_status("승인")
    for page in pages:
        draft_id = await _get_draft_id_from_notion_page(page)
        if not draft_id:
            continue
        try:
            import uuid
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ContentDraft).where(ContentDraft.id == uuid.UUID(draft_id))
                )
                draft = result.scalar_one_or_none()
                if draft and draft.status == "review":
                    from publisher import publish_draft
                    await publish_draft(str(draft.id), draft.channel_type, draft.body_md)
        except Exception as e:
            print(f"[poller] 발행 실패 {draft_id}: {e}")


async def _process_revision():
    """노션에서 '수정 필요' → DB 상태를 'revision'으로 업데이트."""
    pages = await _query_notion_by_status("수정 필요")
    for page in pages:
        draft_id = await _get_draft_id_from_notion_page(page)
        if not draft_id:
            continue
        # 수정 메모 추출
        props = page.get("properties", {})
        memo_rich = props.get("수정 메모", {}).get("rich_text", [])
        memo = memo_rich[0].get("text", {}).get("content", "") if memo_rich else ""
        try:
            import uuid
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ContentDraft).where(ContentDraft.id == uuid.UUID(draft_id))
                )
                draft = result.scalar_one_or_none()
                if draft and draft.status == "review":
                    draft.status        = "revision"
                    draft.revision_memo = memo
                    await db.commit()
        except Exception as e:
            print(f"[poller] 수정 업데이트 실패 {draft_id}: {e}")


async def run_poller():
    """서버 lifespan에서 백그라운드 태스크로 실행."""
    if not NOTION_API_KEY:
        print("[poller] NOTION_API_KEY 없음 — 폴링 비활성화")
        return
    print(f"[poller] 시작 — {POLL_INTERVAL}초 간격")
    while True:
        try:
            await _process_approved()
            await _process_revision()
        except Exception as e:
            print(f"[poller] 오류: {e}")
        await asyncio.sleep(POLL_INTERVAL)
