from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid
from database import get_db
from models import ChannelConfig
from crypto import encrypt

router = APIRouter()

class ChannelCreate(BaseModel):
    user_id: str; channel_type: str; channel_name: str
    api_endpoint: Optional[str] = None
    api_key_enc: Optional[str] = None
    extra_config: Optional[dict] = None

@router.get("/")
async def list_channels(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChannelConfig).where(ChannelConfig.user_id == uuid.UUID(user_id)))
    return [{"id": str(c.id), "channel_type": c.channel_type, "is_active": c.is_active} for c in result.scalars().all()]

@router.post("/")
async def upsert_channel(body: ChannelCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChannelConfig).where(
            ChannelConfig.user_id == uuid.UUID(body.user_id),
            ChannelConfig.channel_type == body.channel_type
        )
    )
    ch = result.scalar_one_or_none()
    if ch:
        ch.channel_name = body.channel_name
        ch.api_endpoint = body.api_endpoint
        if body.api_key_enc:
            ch.api_key_enc = encrypt(body.api_key_enc)
        ch.extra_config = body.extra_config
        ch.is_active = True
    else:
        data = body.dict()
        if data.get("api_key_enc"):
            data["api_key_enc"] = encrypt(data["api_key_enc"])
        ch = ChannelConfig(**{k: (uuid.UUID(v) if k == "user_id" else v)
                              for k, v in data.items()})
        db.add(ch)
    await db.flush()
    return {"id": str(ch.id), "channel_type": ch.channel_type}
