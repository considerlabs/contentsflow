from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import Category, User
from auth import get_current_user, parse_uuid, require_same_user

router = APIRouter()

class CategoryCreate(BaseModel):
    user_id: str; name: str
    description: Optional[str] = None
    color: Optional[str] = None

@router.get("/")
async def list_categories(user_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_user_id = require_same_user(user_id, user)
    result = await db.execute(
        select(Category)
        .where(Category.user_id == parsed_user_id, Category.is_active == True)
        .order_by(Category.sort_order)
    )
    return [{"id": str(c.id), "name": c.name, "color": c.color} for c in result.scalars().all()]

@router.post("/")
async def create_category(body: CategoryCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_user_id = require_same_user(body.user_id, user)
    cat = Category(user_id=parsed_user_id, name=body.name,
                   description=body.description, color=body.color)
    db.add(cat); await db.flush()
    return {"id": str(cat.id), "name": cat.name}

@router.delete("/{category_id}")
async def delete_category(category_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Category).where(Category.id == parse_uuid(category_id, "category_id")))
    cat    = result.scalar_one_or_none()
    if not cat or cat.user_id != user.id: raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")
    cat.is_active = False
    return {"status": "deleted"}
