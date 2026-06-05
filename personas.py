# personas 라우터 — 온보딩 결과 저장·조회·수정
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import json

from database import get_db
from models import UserPersona, User
from agent import call_llm
from auth import get_current_user, parse_uuid, require_same_user

router = APIRouter()

class OnboardingAnswers(BaseModel):
    user_id:     str
    raw_answers: dict

class PersonaUpdate(BaseModel):
    persona_md: str
    style_md:   str
    topic_md:   Optional[str] = ""

PERSONA_SYSTEM = """
너는 콘텐츠 자동화 시스템의 전문가다.
사용자의 온보딩 답변을 분석해서 아래 세 파일을 생성해라.

반드시 JSON 형식으로만 출력하라. 다른 텍스트 없이 JSON만:
{
  "persona_md": "...",
  "style_md": "...",
  "topic_md": "..."
}

각 파일 역할:
- persona_md: 에디터 정체성·경력·핵심가치·절대금지 표현 (마크다운)
- style_md: 말투·문장구조·길이·채널별 포맷 가이드 (마크다운)
- topic_md: 핵심 포지셔닝 한 줄 / 플레이북 주제 / SEO 키워드 목록 / 절대 금지 내용 (마크다운)
"""

@router.post("/generate")
async def generate_persona(
    body: OnboardingAnswers,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_user_id = require_same_user(body.user_id, user)
    prompt = f"온보딩 답변:\n{body.raw_answers}\n\npersona.md, style.md, topic.md 세 파일을 생성하라."
    raw    = await call_llm(prompt, system=PERSONA_SYSTEM)

    try:
        start = raw.find("{"); end = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
    except Exception:
        data  = {"persona_md": raw, "style_md": "", "topic_md": ""}

    result  = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == parsed_user_id)
        .order_by(UserPersona.version.desc()).limit(1)
    )
    latest  = result.scalar_one_or_none()
    version = (latest.version + 1) if latest else 1

    persona = UserPersona(
        user_id     = parsed_user_id,
        raw_answers = body.raw_answers,
        persona_md  = data.get("persona_md", ""),
        style_md    = data.get("style_md", ""),
        topic_md    = data.get("topic_md", ""),
        version     = version
    )
    db.add(persona)
    await db.flush()

    user.onboarding_done = True

    return {"persona_id": str(persona.id), "version": version}


@router.get("/")
async def get_persona(user_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_user_id = require_same_user(user_id, user)
    result = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == parsed_user_id)
        .order_by(UserPersona.version.desc()).limit(1)
    )
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="페르소나가 없습니다.")
    return {
        "id":         str(persona.id),
        "persona_md": persona.persona_md,
        "style_md":   persona.style_md,
        "topic_md":   persona.topic_md or "",
        "version":    persona.version,
    }


@router.put("/{persona_id}")
async def update_persona(
    persona_id: str,
    body: PersonaUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result  = await db.execute(select(UserPersona).where(UserPersona.id == parse_uuid(persona_id, "persona_id")))
    persona = result.scalar_one_or_none()
    if not persona or persona.user_id != user.id:
        raise HTTPException(status_code=404, detail="페르소나를 찾을 수 없습니다.")
    persona.persona_md = body.persona_md
    persona.style_md   = body.style_md
    persona.topic_md   = body.topic_md or ""
    return {"status": "updated"}
