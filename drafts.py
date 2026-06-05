from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import ContentDraft, User
from auth import get_current_user, parse_uuid, require_same_user

router = APIRouter()

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
    return [
        {
            "id":           str(d.id),
            "channel_type": d.channel_type,
            "title":        d.title,
            "qc_passed":    d.qc_passed,
            "has_content":  bool(d.body_md),
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
        }
        for d in drafts
    ]

@router.get("/{draft_id}")
async def get_draft(draft_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == parse_uuid(draft_id, "draft_id")))
    draft  = result.scalar_one_or_none()
    if not draft or draft.user_id != user.id: raise HTTPException(status_code=404, detail="초안을 찾을 수 없습니다.")
    return {"id": str(draft.id), "channel_type": draft.channel_type,
            "body_md": draft.body_md, "status": draft.status,
            "qc_results": draft.qc_results}

@router.delete("/{draft_id}")
async def delete_draft(draft_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == parse_uuid(draft_id, "draft_id")))
    draft  = result.scalar_one_or_none()
    if not draft or draft.user_id != user.id: raise HTTPException(status_code=404, detail="초안을 찾을 수 없습니다.")
    await db.delete(draft)
    return {"status": "deleted"}
