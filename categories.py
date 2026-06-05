from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
from database import get_db
from models import Category

router = APIRouter()

class CategoryCreate(BaseModel):
    user_id: str; name: str
    description: Optional[str] = None
    color: Optional[str] = None

@router.get("/")
async def list_categories(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Category)
        .where(Category.user_id == uuid.UUID(user_id), Category.is_active == True)
        .order_by(Category.sort_order)
    )
    return [{"id": str(c.id), "name": c.name, "color": c.color} for c in result.scalars().all()]

@router.post("/")
async def create_category(body: CategoryCreate, db: AsyncSession = Depends(get_db)):
    cat = Category(user_id=uuid.UUID(body.user_id), name=body.name,
                   description=body.description, color=body.color)
    db.add(cat); await db.flush()
    return {"id": str(cat.id), "name": cat.name}

@router.delete("/{category_id}")
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == uuid.UUID(category_id)))
    cat    = result.scalar_one_or_none()
    if not cat: raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    cat.is_active = False
    return {"status": "deleted"}
