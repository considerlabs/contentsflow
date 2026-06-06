from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import ContentDraft, TopicProposal, User
from auth import get_current_user, parse_uuid, require_same_user

router = APIRouter()


async def research_session_ids_for(drafts: list[ContentDraft], db: AsyncSession) -> set:
    session_ids = [d.session_id for d in drafts if d.session_id]
    if not session_ids:
        return set()
    result = await db.execute(
        select(TopicProposal.session_id).where(TopicProposal.session_id.in_(session_ids))
    )
    return set(result.scalars().all())


def draft_source_meta(draft: ContentDraft, research_session_ids: set = None) -> dict:
    meta = draft.meta or {}
    is_research_session = bool(research_session_ids and draft.session_id in research_session_ids)
    source_type = meta.get("source_type") or ("research" if is_research_session else "manual")
    source_label = meta.get("source_label")
    if not source_label:
        source_label = "자동 리서치" if source_type == "research" else "수동 생성"
    return {
        "source_type": source_type,
        "source_label": source_label,
    }


@router.get("/pending")
async def list_pending_drafts(user_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_user_id = require_same_user(user_id, user)
    result = await db.execute(
        select(ContentDraft).where(
            ContentDraft.user_id == parsed_user_id,
            ContentDraft.status  == "review"
        ).order_by(ContentDraft.created_at.desc())
    )
    drafts = result.scalars().all()
    research_session_ids = await research_session_ids_for(drafts, db)
    return [
        {
            "id":           str(d.id),
            "channel_type": d.channel_type,
            "title":        d.title,
            "qc_passed":    d.qc_passed,
            "has_content":  bool(d.body_md),
            **draft_source_meta(d, research_session_ids),
        }
        for d in drafts
    ]

@router.get("/published")
async def list_published_drafts(
    user_id: str,
    channel_type: str = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_user_id = require_same_user(user_id, user)
    SHOW_STATUSES = ("review", "approved", "revision", "rejected", "published", "publish_failed")
    q = select(ContentDraft).where(
        ContentDraft.user_id == parsed_user_id,
        ContentDraft.status.in_(SHOW_STATUSES),
        ContentDraft.body_md != None,
        ContentDraft.body_md != "",
    )
    if channel_type:
        q = q.where(ContentDraft.channel_type == channel_type)
    q = q.order_by(ContentDraft.created_at.desc())
    result = await db.execute(q)
    drafts = result.scalars().all()
    research_session_ids = await research_session_ids_for(drafts, db)
    return [
        {
            "id":            str(d.id),
            "channel_type":  d.channel_type,
            "title":         d.title,
            "status":        d.status,
            "created_at":    d.created_at.isoformat() if d.created_at else None,
            "published_at":  d.published_at.isoformat() if d.published_at else None,
            "published_url": d.published_url,
            "qc_passed":     d.qc_passed,
            "generation_ms": d.generation_ms,
            **draft_source_meta(d, research_session_ids),
        }
        for d in drafts
    ]

@router.get("/{draft_id}")
async def get_draft(draft_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == parse_uuid(draft_id, "draft_id")))
    draft  = result.scalar_one_or_none()
    if not draft or draft.user_id != user.id: raise HTTPException(status_code=404, detail="초안을 찾을 수 없습니다.")
    research_session_ids = await research_session_ids_for([draft], db)
    return {"id": str(draft.id), "channel_type": draft.channel_type,
            "body_md": draft.body_md, "status": draft.status,
            "qc_results": draft.qc_results, **draft_source_meta(draft, research_session_ids)}

@router.delete("/{draft_id}")
async def delete_draft(draft_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == parse_uuid(draft_id, "draft_id")))
    draft  = result.scalar_one_or_none()
    if not draft or draft.user_id != user.id: raise HTTPException(status_code=404, detail="초안을 찾을 수 없습니다.")
    await db.delete(draft)
    return {"status": "deleted"}
