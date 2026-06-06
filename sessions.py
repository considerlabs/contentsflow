# ============================================
# ContentFlow — 콘텐츠 세션 라우터 (핵심)
# ============================================
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import uuid

from database import get_db
from models import (
    ContentSession, ContentDraft, UserPersona,
    Category, Keyword, ReviewLog, TopicProposal, User
)
from agent import (
    SUPPORTED_CHANNELS,
    generate_draft,
    generate_source_package,
    generate_topic_candidates,
    load_knowledge,
    run_qc,
)
from auth import get_current_user, parse_uuid, require_same_user
import notion

router = APIRouter()


def _to_uuid(value: Optional[str], field_name: str) -> Optional[uuid.UUID]:
    if not value:
        return None
    return parse_uuid(value, field_name)


async def _get_owned_session(db: AsyncSession, session_id: str, user: User) -> ContentSession:
    parsed_session_id = _to_uuid(session_id, "session_id")
    result = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return session


async def _session_cancel_requested(db: AsyncSession, session_id: uuid.UUID) -> bool:
    result = await db.execute(select(ContentSession).where(ContentSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return True
    return session.status in {"cancel_requested", "cancelled"}


async def _mark_session_cancelled(db: AsyncSession, session_id: uuid.UUID, message: str = "사용자가 생성을 중단했습니다.") -> None:
    result = await db.execute(select(ContentSession).where(ContentSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return
    session.status = "cancelled"
    session.error_message = message
    session.generation_current_channel = None
    proposal_result = await db.execute(select(TopicProposal).where(TopicProposal.session_id == session.id))
    proposal = proposal_result.scalar_one_or_none()
    if proposal:
        proposal.status = "cancelled"
    await db.commit()


# ── 스키마 ───────────────────────────────────
class SessionCreate(BaseModel):
    user_id:       str
    category_id:   Optional[str] = None
    keyword_id:    Optional[str] = None
    input_keyword: str
    input_emotion: Optional[str] = None
    input_memo:    Optional[str] = None
    input_exclude: Optional[str] = None

class TopicSelect(BaseModel):
    selected_topic: dict
    channels:       list[str]  # ["blog","newsletter","youtube","shortform"]

class ReviewAction(BaseModel):
    action: str   # approved | revision | rejected
    memo:   Optional[str] = None


# ── 1. 세션 생성 + 주제 후보 생성 ─────────────
@router.post("/")
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    user_id = require_same_user(body.user_id, user)
    category_id = _to_uuid(body.category_id, "category_id")
    keyword_id = _to_uuid(body.keyword_id, "keyword_id")

    if category_id:
        category_result = await db.execute(
            select(Category).where(Category.id == category_id, Category.user_id == user_id)
        )
        if not category_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다.")

    if keyword_id:
        keyword_result = await db.execute(
            select(Keyword).where(Keyword.id == keyword_id, Keyword.user_id == user_id)
        )
        if not keyword_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")

    # 사용자 페르소나 조회
    result = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == user_id)
        .order_by(UserPersona.version.desc())
        .limit(1)
    )
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="페르소나 파일이 없습니다. 온보딩을 완료해 주세요.")

    # 키워드 목록 조회
    kw_result = await db.execute(
        select(Keyword.keyword)
        .where(Keyword.user_id == user_id, Keyword.is_active == True)
    )
    keywords = [row[0] for row in kw_result.fetchall()]

    # 오케스트레이터 — 주제 후보 생성
    knowledge  = load_knowledge("", persona.persona_md, persona.style_md, keywords,
                                topic_md=persona.topic_md or "")
    try:
        candidates = await generate_topic_candidates(
            knowledge,
            body.input_keyword,
            body.input_emotion or "",
            body.input_exclude or ""
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 세션 저장
    session = ContentSession(
        user_id          = user_id,
        category_id      = category_id,
        keyword_id       = keyword_id,
        input_keyword    = body.input_keyword,
        input_emotion    = body.input_emotion,
        input_memo       = body.input_memo,
        input_exclude    = body.input_exclude,
        topic_candidates = candidates,
        status           = "topic_select"
    )
    db.add(session)
    await db.flush()

    return {
        "session_id":       str(session.id),
        "topic_candidates": candidates
    }


# ── 2. 주제 선택 + 채널별 초안 생성 ──────────
@router.post("/{session_id}/generate")
async def generate_drafts(
    session_id: str,
    body: TopicSelect,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_session_id = _to_uuid(session_id, "session_id")
    result  = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    if session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session.selected_topic = body.selected_topic
    session.status         = "generating"
    session.error_message  = None
    session.generation_done = 0
    session.generation_total = len(body.channels)
    session.generation_current_channel = "source_package"

    if not body.selected_topic.get("title"):
        raise HTTPException(status_code=400, detail="선택한 주제에 title이 필요합니다.")
    invalid_channels = [ch for ch in body.channels if ch not in SUPPORTED_CHANNELS]
    if invalid_channels:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 채널입니다: {', '.join(invalid_channels)}")
    if not body.channels:
        raise HTTPException(status_code=400, detail="생성할 채널을 1개 이상 선택해 주세요.")

    await db.commit()

    # 백그라운드에서 초안 생성
    background_tasks.add_task(
        _run_generation,
        str(session.user_id),
        session_id,
        body.selected_topic,
        body.channels,
        session.input_emotion or "",
        session.input_memo    or "",
        session.input_exclude or ""
    )

    return {"status": "generating", "session_id": session_id}


async def _run_generation(
    user_id: str, session_id: str,
    selected_topic: dict, channels: list,
    input_emotion: str, input_memo: str, input_exclude: str
):
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            # 페르소나 재조회
            result  = await db.execute(
                select(UserPersona)
                .where(UserPersona.user_id == _to_uuid(user_id, "user_id"))
                .order_by(UserPersona.version.desc()).limit(1)
            )
            persona  = result.scalar_one_or_none()
            if not persona:
                raise RuntimeError("페르소나 파일이 없습니다. 온보딩을 다시 완료해 주세요.")

            kw_result = await db.execute(
                select(Keyword.keyword)
                .where(Keyword.user_id == _to_uuid(user_id, "user_id"), Keyword.is_active == True)
            )
            keywords = [row[0] for row in kw_result.fetchall()]

            parsed_user_id = _to_uuid(user_id, "user_id")
            parsed_session_id = _to_uuid(session_id, "session_id")
            knowledge = load_knowledge("", persona.persona_md, persona.style_md, keywords, topic_md=persona.topic_md or "")

            result = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
            session = result.scalar_one_or_none()
            if not session:
                raise RuntimeError("세션을 찾을 수 없습니다.")
            session.status = "generating"
            session.error_message = None
            session.generation_done = 0
            session.generation_total = len(channels)
            session.generation_current_channel = "source_package"
            await db.commit()

            source_package = await generate_source_package(
                knowledge, selected_topic, input_emotion, input_memo, input_exclude
            )
            if await _session_cancel_requested(db, parsed_session_id):
                await _mark_session_cancelled(db, parsed_session_id)
                return

            saved_drafts = []
            for ch in channels:
                if await _session_cancel_requested(db, parsed_session_id):
                    await _mark_session_cancelled(db, parsed_session_id)
                    return

                result = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
                session = result.scalar_one_or_none()
                if not session:
                    return
                session.generation_current_channel = ch
                await db.commit()

                d = await generate_draft(knowledge, source_package, selected_topic, ch, input_emotion, input_memo)
                if await _session_cancel_requested(db, parsed_session_id):
                    await _mark_session_cancelled(db, parsed_session_id)
                    return
                qc = await run_qc(d["body_md"], ch)
                draft = ContentDraft(
                    session_id    = parsed_session_id,
                    user_id       = parsed_user_id,
                    channel_type  = d["channel_type"],
                    title         = d.get("title", ""),
                    body_md       = d["body_md"],
                    body_html     = d.get("body_html") or None,
                    meta          = {"source_package": d.get("source_package")},
                    qc_passed     = qc["passed"],
                    qc_results    = qc["results"],
                    llm_model     = d["llm_model"],
                    generation_ms = d["generation_ms"],
                    status        = "review"
                )
                db.add(draft)
                saved_drafts.append(draft)
                await db.flush()

                result = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
                session = result.scalar_one_or_none()
                if not session:
                    return
                session.generation_done = (session.generation_done or 0) + 1
                session.generation_current_channel = None
                await db.commit()

                try:
                    notion_id = await notion.register_draft(
                        draft_id     = str(draft.id),
                        title        = draft.title or "",
                        channel_type = draft.channel_type,
                        keyword      = selected_topic.get("title", ""),
                    )
                    if notion_id:
                        draft.notion_page_id = notion_id
                        await db.commit()
                except Exception as exc:
                    draft.revision_memo = f"노션 등록 실패: {exc}"
                    await db.commit()

            # 세션 상태 업데이트
            result  = await db.execute(select(ContentSession).where(ContentSession.id == parsed_session_id))
            session = result.scalar_one()
            session.status = "review"
            session.error_message = None
            session.generation_current_channel = None
            session.generation_done = len(saved_drafts)
            session.generation_total = len(channels)
            proposal_result = await db.execute(
                select(TopicProposal).where(TopicProposal.session_id == session.id)
            )
            proposal = proposal_result.scalar_one_or_none()
            if proposal:
                proposal.status = "generated"

            await db.commit()
        except Exception as exc:
            await db.rollback()
            async with AsyncSessionLocal() as fail_db:
                result = await fail_db.execute(
                    select(ContentSession).where(ContentSession.id == _to_uuid(session_id, "session_id"))
                )
                session = result.scalar_one_or_none()
                if session:
                    session.status = "failed"
                    session.error_message = str(exc)
                    session.generation_current_channel = None
                    try:
                        proposal_result = await fail_db.execute(
                            select(TopicProposal).where(TopicProposal.session_id == session.id)
                        )
                        proposal = proposal_result.scalar_one_or_none()
                        if proposal:
                            proposal.status = "failed"
                    except Exception:
                        pass
                    await fail_db.commit()


# ── 3. 검수 — 승인 / 수정 / 반려 ─────────────
@router.post("/drafts/{draft_id}/review")
async def review_draft(
    draft_id: str,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parsed_draft_id = _to_uuid(draft_id, "draft_id")
    result = await db.execute(select(ContentDraft).where(ContentDraft.id == parsed_draft_id))
    draft  = result.scalar_one_or_none()
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="초안을 찾을 수 없습니다.")
    if body.action not in {"approved", "revision", "rejected"}:
        raise HTTPException(status_code=400, detail="action은 approved, revision, rejected 중 하나여야 합니다.")

    draft.status        = body.action       # approved | revision | rejected
    draft.revision_memo = body.memo

    log = ReviewLog(
        draft_id = draft.id,
        user_id  = draft.user_id,
        action   = body.action,
        memo     = body.memo
    )
    db.add(log)

    # 노션 상태 업데이트 (실패해도 계속)
    try:
        await notion.update_status(
            notion_page_id = draft.notion_page_id or "",
            status         = body.action,
            revision_memo  = body.memo or "",
        )
    except Exception:
        pass

    # 승인 시 선택 채널 발행 시도. 채널 설정이 없으면 publisher가 상태/메모를 남긴다.
    if body.action == "approved":
        await db.commit()
        from publisher import publish_draft
        await publish_draft(str(draft.id), draft.channel_type, draft.body_md)

    return {"status": body.action, "draft_id": draft_id}


# ── 4. 세션 중단/삭제 ─────────────────────────
@router.post("/{session_id}/cancel")
async def cancel_session(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    session = await _get_owned_session(db, session_id, user)
    if session.status in {"review", "failed", "cancelled"}:
        return {"status": session.status, "session_id": session_id}
    session.status = "cancel_requested"
    session.error_message = "사용자가 생성을 중단했습니다. 현재 LLM 호출이 끝나면 안전하게 멈춥니다."
    proposal_result = await db.execute(select(TopicProposal).where(TopicProposal.session_id == session.id))
    proposal = proposal_result.scalar_one_or_none()
    if proposal:
        proposal.status = "cancel_requested"
    return {"status": "cancel_requested", "session_id": session_id}


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    session = await _get_owned_session(db, session_id, user)
    proposal_result = await db.execute(select(TopicProposal).where(TopicProposal.session_id == session.id))
    proposal = proposal_result.scalar_one_or_none()
    if proposal:
        proposal.status = "proposed"
        proposal.session_id = None
    await db.delete(session)
    return {"status": "deleted", "session_id": session_id}


# ── 5. 세션 상태 조회 ─────────────────────────
@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    parsed_session_id = _to_uuid(session_id, "session_id")
    result  = await db.execute(
        select(ContentSession)
        .where(ContentSession.id == parsed_session_id)
    )
    session = result.scalar_one_or_none()
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 초안 목록도 함께 반환
    drafts_result = await db.execute(
        select(ContentDraft).where(ContentDraft.session_id == session.id, ContentDraft.user_id == user.id)
    )
    drafts = drafts_result.scalars().all()

    return {
        "session_id":       str(session.id),
        "status":           session.status,
        "topic_candidates": session.topic_candidates,
        "selected_topic":   session.selected_topic,
        "error_message":    session.error_message,
        "generation_current_channel": session.generation_current_channel,
        "generation_done":  session.generation_done or 0,
        "generation_total": session.generation_total or 0,
        "drafts": [
            {
                "draft_id":     str(d.id),
                "channel_type": d.channel_type,
                "status":       d.status,
                "qc_passed":    d.qc_passed,
                "title":        d.title
            }
            for d in drafts
        ]
    }
