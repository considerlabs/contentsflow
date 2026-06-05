from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid
from database import get_db
from models import User

router = APIRouter()

class UserCreate(BaseModel):
    email: str; name: str

@router.post("/")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(email=body.email, name=body.name)
    db.add(user); await db.flush()
    return {"id": str(user.id), "email": user.email}

@router.get("/{user_id}")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"id": str(user.id), "name": user.name, "onboarding_done": user.onboarding_done}
