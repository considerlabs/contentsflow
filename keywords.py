from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
from database import get_db
from models import Keyword

router = APIRouter()

class KeywordCreate(BaseModel):
    user_id: str; category_id: str; keyword: str
    target_emotion: Optional[str] = None
    memo: Optional[str] = None
    exclude_topics: Optional[str] = None

@router.get("/")
async def list_keywords(user_id: str, category_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = select(Keyword).where(Keyword.user_id == uuid.UUID(user_id), Keyword.is_active == True)
    if category_id:
        q = q.where(Keyword.category_id == uuid.UUID(category_id))
    result = await db.execute(q)
    return [{"id": str(k.id), "keyword": k.keyword, "usage_count": k.usage_count} for k in result.scalars().all()]

@router.post("/")
async def create_keyword(body: KeywordCreate, db: AsyncSession = Depends(get_db)):
    kw = Keyword(user_id=uuid.UUID(body.user_id), category_id=uuid.UUID(body.category_id),
                 keyword=body.keyword, target_emotion=body.target_emotion,
                 memo=body.memo, exclude_topics=body.exclude_topics)
    db.add(kw); await db.flush()
    return {"id": str(kw.id), "keyword": kw.keyword}

@router.delete("/{keyword_id}")
async def delete_keyword(keyword_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Keyword).where(Keyword.id == uuid.UUID(keyword_id)))
    kw     = result.scalar_one_or_none()
    if not kw: raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")
    kw.is_active = False
    return {"status": "deleted"}
