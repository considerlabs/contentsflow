import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User


JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("ENCRYPTION_KEY") or "dev-contentflow-jwt-secret"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", str(60 * 60 * 24 * 30)))
security = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode())


def _sign(message: str) -> str:
    digest = hmac.new(JWT_SECRET.encode(), message.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def create_access_token(user: User) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    header_part = _b64encode(json.dumps(header, separators=(",", ":")).encode())
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(f"{header_part}.{payload_part}")
    return f"{header_part}.{payload_part}.{signature}"


def decode_access_token(token: str) -> dict:
    try:
        header_part, payload_part, signature = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="인증 토큰 형식이 올바르지 않습니다.") from exc

    expected = _sign(f"{header_part}.{payload_part}")
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="인증 토큰 서명이 올바르지 않습니다.")

    try:
        payload = json.loads(_b64decode(payload_part))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="인증 토큰 내용을 읽을 수 없습니다.") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="인증 토큰이 만료되었습니다.")
    return payload


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="인증 토큰의 사용자 ID가 올바르지 않습니다.") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")
    return user


def user_payload(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "onboarding_done": bool(user.onboarding_done),
    }


def parse_uuid(value: Optional[str], field_name: str) -> uuid.UUID:
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} 값이 필요합니다.")
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 값이 올바른 UUID가 아닙니다.") from exc


def require_same_user(user_id: str, current_user: User) -> uuid.UUID:
    parsed_user_id = parse_uuid(user_id, "user_id")
    if parsed_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="다른 사용자의 데이터에 접근할 수 없습니다.")
    return parsed_user_id
