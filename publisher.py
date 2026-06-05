# ============================================
# ContentFlow — 발행 모듈
# ============================================
import httpx
from sqlalchemy import select
from database import AsyncSessionLocal
from models import ContentDraft, ChannelConfig
import uuid
from datetime import datetime, timezone
import notion
from crypto import decrypt


async def publish_draft(draft_id: str, channel_type: str, body_md: str):
    async with AsyncSessionLocal() as db:
        # 초안 조회
        result = await db.execute(
            select(ContentDraft).where(ContentDraft.id == uuid.UUID(draft_id))
        )
        draft = result.scalar_one_or_none()
        if not draft:
            return

        # 채널 설정 조회
        ch_result = await db.execute(
            select(ChannelConfig).where(
                ChannelConfig.user_id     == draft.user_id,
                ChannelConfig.channel_type == channel_type,
                ChannelConfig.is_active   == True
            )
        )
        channel = ch_result.scalar_one_or_none()
        if not channel:
            if channel_type == "blog":
                draft.status = "publish_failed"
                draft.revision_memo = "채널 설정이 없습니다."
            else:
                draft.status = "approved"
                draft.revision_memo = "채널 설정이 없어 자동 발행 없이 승인 상태로 보관합니다."
            await db.commit()
            return

        # 채널별 발행 처리
        api_key = decrypt(channel.api_key_enc or "")
        published_url = None
        try:
            if channel_type == "blog":
                published_url = await _publish_blog(channel, draft.title, body_md, api_key)
            elif channel_type == "newsletter":
                published_url = await _publish_newsletter(channel, draft.title, draft.body_html or body_md, api_key)
            elif channel_type in ("youtube", "shortform"):
                published_url = await _save_to_drive(channel, draft.title, body_md, channel_type, api_key)
            else:
                raise ValueError(f"지원하지 않는 채널입니다: {channel_type}")

            draft.status        = "published"
            draft.published_at  = datetime.now(timezone.utc)
            draft.published_url = published_url

            # 노션 발행 완료 업데이트 (실패해도 계속)
            try:
                await notion.update_status(
                    notion_page_id = draft.notion_page_id or "",
                    status         = "published",
                    published_url  = published_url or "",
                )
            except Exception:
                pass

        except Exception as e:
            draft.status        = "publish_failed"
            draft.revision_memo = str(e)

        await db.commit()


async def _publish_blog(channel: ChannelConfig, title: str, body: str, api_key: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            channel.api_endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"title": title, "content": body, "visibility": "public"}
        )
        res.raise_for_status()
        data = res.json()
        return data.get("url", "")


async def _publish_newsletter(channel: ChannelConfig, title: str, body_html: str, api_key: str) -> str:
    extra = channel.extra_config or {}
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            channel.api_endpoint,
            headers={"X-Stibee-Api-Key": api_key},
            json={
                "name":      title,
                "subject":   title,
                "contents":  body_html,
                "listId":    extra.get("list_id", "")
            }
        )
        res.raise_for_status()
        return res.json().get("url", "")


async def _save_to_drive(channel: ChannelConfig, title: str, body: str, channel_type: str, api_key: str) -> str:
    extra    = channel.extra_config or {}
    folder   = extra.get("folder_id", "")
    filename = f"[{channel_type}] {title}.md"
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                "metadata": (None, f'{{"name":"{filename}","parents":["{folder}"]}}', "application/json"),
                "file":     (filename, body.encode(), "text/markdown")
            }
        )
        res.raise_for_status()
        file_id = res.json().get("id", "")
        return f"https://drive.google.com/file/d/{file_id}"
