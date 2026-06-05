from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from database import get_db
from models import User
from auth import create_access_token, get_current_user, parse_uuid, user_payload

router = APIRouter()

class UserCreate(BaseModel):
    email: str; name: str

class LoginRequest(BaseModel):
    email: str
    name: str = ""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _auth_response(user: User) -> dict:
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_payload(user)}

@router.post("/")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    email = _normalize_email(body.email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        if body.name and body.name != user.name:
            user.name = body.name
        await db.flush()
        return {"id": str(user.id), "email": user.email}

    user = User(email=email, name=body.name)
    db.add(user)
    await db.flush()
    return {"id": str(user.id), "email": user.email}


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = _normalize_email(body.email)
    if not email:
        raise HTTPException(status_code=400, detail="이메일을 입력해 주세요.")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        if body.name and body.name != user.name:
            user.name = body.name
        await db.flush()
        return _auth_response(user)

    user = User(email=email, name=body.name or email.split("@")[0])
    db.add(user)
    await db.flush()
    return _auth_response(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user_payload(user)

@router.get("/{user_id}")
async def get_user(user_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    parsed_user_id = parse_uuid(user_id, "user_id")
    if parsed_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="다른 사용자의 정보에 접근할 수 없습니다.")
    result = await db.execute(select(User).where(User.id == parsed_user_id))
    user   = result.scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return {"id": str(user.id), "name": user.name, "onboarding_done": user.onboarding_done}
