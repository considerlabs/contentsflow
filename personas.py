# personas 라우터 — 온보딩 결과 저장·조회·수정
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid

from database import get_db
from models import UserPersona, User
from agent import call_llm

router = APIRouter()

class OnboardingAnswers(BaseModel):
    user_id:     str
    raw_answers: dict   # 온보딩 전체 답변

class PersonaUpdate(BaseModel):
    persona_md: str
    style_md:   str

PERSONA_SYSTEM = """
너는 콘텐츠 자동화 시스템의 페르소나 생성 전문가다.
사용자의 온보딩 답변을 분석해서 persona.md와 style.md 두 파일을 생성해라.
반드시 JSON 형식으로만 출력하라:
{"persona_md": "...", "style_md": "..."}
"""

@router.post("/generate")
async def generate_persona(body: OnboardingAnswers, db: AsyncSession = Depends(get_db)):
    prompt = f"온보딩 답변:\n{body.raw_answers}\n\npersona.md와 style.md를 생성하라."
    raw    = await call_llm(prompt, system=PERSONA_SYSTEM)

    import json
    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
    except Exception:
        data  = {"persona_md": raw, "style_md": ""}

    # 기존 버전 조회
    result  = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == uuid.UUID(body.user_id))
        .order_by(UserPersona.version.desc()).limit(1)
    )
    latest  = result.scalar_one_or_none()
    version = (latest.version + 1) if latest else 1

    persona = UserPersona(
        user_id     = uuid.UUID(body.user_id),
        raw_answers = body.raw_answers,
        persona_md  = data["persona_md"],
        style_md    = data["style_md"],
        version     = version
    )
    db.add(persona)
    await db.flush()

    # 온보딩 완료 처리
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(body.user_id)))
    user = user_result.scalar_one_or_none()
    if user:
        user.onboarding_done = True

    return {"persona_id": str(persona.id), "version": version}


@router.get("/")
async def get_persona(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == uuid.UUID(user_id))
        .order_by(UserPersona.version.desc()).limit(1)
    )
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="페르소나가 없습니다.")
    return {
        "id":         str(persona.id),
        "persona_md": persona.persona_md,
        "style_md":   persona.style_md,
        "version":    persona.version,
    }


@router.put("/{persona_id}")
async def update_persona(persona_id: str, body: PersonaUpdate, db: AsyncSession = Depends(get_db)):
    result  = await db.execute(select(UserPersona).where(UserPersona.id == uuid.UUID(persona_id)))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    persona.persona_md = body.persona_md
    persona.style_md   = body.style_md
    return {"status": "updated"}
