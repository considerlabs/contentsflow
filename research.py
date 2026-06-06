import asyncio
import html
import os
import smtplib
from datetime import datetime, time as dt_time, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent import SUPPORTED_CHANNELS, generate_researched_topic_proposals, load_knowledge
from auth import get_current_user, parse_uuid
from database import AsyncSessionLocal, get_db
from models import (
    ContentSession,
    Keyword,
    ResearchItem,
    ResearchRun,
    ResearchSource,
    TopicProposal,
    User,
    UserPersona,
)
import notion

router = APIRouter()

RESEARCH_DAILY_TIME = os.getenv("RESEARCH_DAILY_TIME", "05:30")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
MAX_ITEMS_PER_SOURCE = int(os.getenv("RESEARCH_MAX_ITEMS_PER_SOURCE", "10"))


class ResearchSourceCreate(BaseModel):
    name: str
    url: str
    source_type: str = "rss"


class ProposalSelect(BaseModel):
    channels: list[str] = Field(default_factory=lambda: list(SUPPORTED_CHANNELS))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Optional[str]) -> str:
    return html.unescape((value or "").strip())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _first_text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    wanted = {name.lower() for name in names}
    for child in node.iter():
        if _local_name(child.tag) in wanted and child.text:
            return _text(child.text)
    return ""


def _first_link(node: ElementTree.Element) -> str:
    for child in node.iter():
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text:
            return child.text.strip()
    return ""


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _strip_html(value: str) -> str:
    text = html.unescape(value or "")
    out = []
    inside = False
    for char in text:
        if char == "<":
            inside = True
            continue
        if char == ">":
            inside = False
            continue
        if not inside:
            out.append(char)
    return " ".join("".join(out).split())


async def _fetch_rss(source: ResearchSource) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        res = await client.get(source.url)
        res.raise_for_status()
    root = ElementTree.fromstring(res.content)
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    items = []
    for entry in entries[:MAX_ITEMS_PER_SOURCE]:
        title = _first_text(entry, ("title",))
        link = _first_link(entry)
        summary = _first_text(entry, ("description", "summary", "content", "encoded"))
        published = _parse_date(_first_text(entry, ("pubDate", "published", "updated", "dc:date")))
        if not title:
            continue
        items.append({
            "title": title,
            "url": link,
            "summary": _strip_html(summary)[:700],
            "published_at": published,
            "source": source.name,
            "raw": {"source_url": source.url},
        })
    return items


async def _fetch_site(source: ResearchSource) -> list[dict]:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        res = await client.get(source.url)
        res.raise_for_status()
    body = res.text
    lower = body.lower()
    title = source.name
    start = lower.find("<title")
    if start >= 0:
        start = lower.find(">", start) + 1
        end = lower.find("</title>", start)
        if start > 0 and end > start:
            title = _strip_html(body[start:end]) or title
    return [{
        "title": title,
        "url": source.url,
        "summary": _strip_html(body)[:700],
        "published_at": None,
        "source": source.name,
        "raw": {"source_url": source.url},
    }]


async def _collect_source(source: ResearchSource) -> list[dict]:
    if source.source_type == "site":
        items = await _fetch_site(source)
    else:
        items = await _fetch_rss(source)
    for item in items:
        item["source_id"] = source.id
    return items


async def _build_knowledge(db: AsyncSession, user_id) -> str:
    persona_result = await db.execute(
        select(UserPersona)
        .where(UserPersona.user_id == user_id)
        .order_by(UserPersona.version.desc())
        .limit(1)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise RuntimeError("페르소나가 없어 새벽 리서치를 실행할 수 없습니다.")

    kw_result = await db.execute(
        select(Keyword.keyword).where(Keyword.user_id == user_id, Keyword.is_active == True)
    )
    keywords = [row[0] for row in kw_result.fetchall()]
    return load_knowledge("", persona.persona_md, persona.style_md, keywords, topic_md=persona.topic_md or "")


async def _notify_email(user: User, proposals: list[TopicProposal]) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "")
    if not smtp_host:
        return False
    to_email = os.getenv("NOTIFICATION_EMAIL") or user.email
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM") or smtp_user or to_email

    lines = ["오늘 새벽 수집 자료 기반 추천 주제 5개입니다.", ""]
    for idx, proposal in enumerate(proposals, 1):
        lines.append(f"{idx}. {proposal.title}")
        if proposal.message:
            lines.append(f"   - {proposal.message}")
        lines.append("")
    lines.append(f"선택 및 생성: {APP_BASE_URL}/auto-content")

    msg = EmailMessage()
    msg["Subject"] = "[ContentFlow] 오늘의 콘텐츠 주제 5개"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content("\n".join(lines))

    def _send():
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if smtp_user:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)

    await asyncio.to_thread(_send)
    return True


async def _notify_notion(proposals: list[TopicProposal]) -> bool:
    if not notion.NOTION_API_KEY:
        return False
    title = "ContentFlow 오늘의 콘텐츠 주제 5개"
    body = "\n".join([f"{idx}. {p.title}\n{p.message or ''}" for idx, p in enumerate(proposals, 1)])
    try:
        await notion.register_topic_digest(title, body, f"{APP_BASE_URL}/auto-content")
        return True
    except Exception:
        return False


async def run_research_for_user(user_id: str) -> str:
    parsed_user_id = parse_uuid(user_id, "user_id")
    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.id == parsed_user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise RuntimeError("사용자를 찾을 수 없습니다.")

        run = ResearchRun(user_id=parsed_user_id, status="collecting", started_at=_utcnow())
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()

        try:
            sources_result = await db.execute(
                select(ResearchSource).where(
                    ResearchSource.user_id == parsed_user_id,
                    ResearchSource.is_active == True,
                )
            )
            sources = sources_result.scalars().all()
            if not sources:
                raise RuntimeError("활성화된 리서치 소스가 없습니다. 설정에서 RSS 또는 사이트를 추가해 주세요.")

            collected = []
            for source in sources:
                try:
                    source_items = await _collect_source(source)
                    source.last_checked_at = _utcnow()
                    collected.extend(source_items)
                except Exception as exc:
                    collected.append({
                        "title": f"{source.name} 수집 실패",
                        "url": source.url,
                        "summary": str(exc),
                        "published_at": None,
                        "source": source.name,
                        "source_id": source.id,
                        "raw": {"error": str(exc)},
                    })

            seen = set()
            unique_items = []
            for item in collected:
                key = item.get("url") or item.get("title")
                if not key or key in seen:
                    continue
                seen.add(key)
                unique_items.append(item)

            if not unique_items:
                raise RuntimeError("수집된 자료가 없습니다.")

            for item in unique_items[:60]:
                db.add(ResearchItem(
                    run_id=run.id,
                    user_id=parsed_user_id,
                    source_id=item.get("source_id"),
                    title=item["title"],
                    url=item.get("url"),
                    summary=item.get("summary"),
                    published_at=item.get("published_at"),
                    raw=item.get("raw"),
                ))
            run.item_count = min(len(unique_items), 60)

            knowledge = await _build_knowledge(db, parsed_user_id)
            proposals = await generate_researched_topic_proposals(knowledge, unique_items, count=5)
            saved_proposals = []
            for proposal in proposals[:5]:
                saved = TopicProposal(
                    run_id=run.id,
                    user_id=parsed_user_id,
                    title=proposal.get("title", ""),
                    message=proposal.get("message", ""),
                    rationale=proposal.get("rationale", ""),
                    evidence=proposal.get("evidence", []),
                    channels=proposal.get("channels") or list(SUPPORTED_CHANNELS),
                    status="proposed",
                )
                db.add(saved)
                saved_proposals.append(saved)

            run.status = "topic_ready"
            run.finished_at = _utcnow()
            await db.flush()

            sent_email = await _notify_email(user, saved_proposals)
            sent_notion = await _notify_notion(saved_proposals)
            run.notification_sent = sent_email or sent_notion
            await db.commit()
            return str(run.id)
        except Exception as exc:
            await db.rollback()
            async with AsyncSessionLocal() as fail_db:
                result = await fail_db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                failed = result.scalar_one_or_none()
                if failed:
                    failed.status = "failed"
                    failed.error_message = str(exc)
                    failed.finished_at = _utcnow()
                    await fail_db.commit()
            raise


async def run_due_research_once() -> None:
    async with AsyncSessionLocal() as db:
        users_result = await db.execute(select(User).where(User.onboarding_done == True))
        users = users_result.scalars().all()
        since = _utcnow() - timedelta(hours=20)
        due_user_ids = []
        for user in users:
            recent_result = await db.execute(
                select(ResearchRun)
                .where(ResearchRun.user_id == user.id, ResearchRun.started_at >= since)
                .order_by(ResearchRun.started_at.desc())
                .limit(1)
            )
            if not recent_result.scalar_one_or_none():
                due_user_ids.append(str(user.id))

    for user_id in due_user_ids:
        try:
            await run_research_for_user(user_id)
        except Exception:
            pass


async def research_scheduler() -> None:
    while True:
        now = datetime.now()
        hour, minute = [int(part) for part in RESEARCH_DAILY_TIME.split(":", 1)]
        target = datetime.combine(now.date(), dt_time(hour=hour, minute=minute))
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep(max((target - now).total_seconds(), 60))
        await run_due_research_once()


@router.get("/sources")
async def list_sources(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(
        select(ResearchSource)
        .where(ResearchSource.user_id == user.id, ResearchSource.is_active == True)
        .order_by(ResearchSource.created_at.desc())
    )
    return [
        {
            "id": str(source.id),
            "name": source.name,
            "url": source.url,
            "source_type": source.source_type,
            "last_checked_at": source.last_checked_at.isoformat() if source.last_checked_at else None,
        }
        for source in result.scalars().all()
    ]


@router.post("/sources")
async def create_source(
    body: ResearchSourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.source_type not in {"rss", "site"}:
        raise HTTPException(status_code=400, detail="source_type은 rss 또는 site만 지원합니다.")
    parsed = urlparse(body.url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="URL은 http 또는 https로 시작해야 합니다.")
    source = ResearchSource(
        user_id=user.id,
        name=body.name.strip() or parsed.netloc,
        url=body.url.strip(),
        source_type=body.source_type,
    )
    db.add(source)
    await db.flush()
    return {"id": str(source.id), "name": source.name, "url": source.url, "source_type": source.source_type}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(ResearchSource).where(ResearchSource.id == parse_uuid(source_id, "source_id")))
    source = result.scalar_one_or_none()
    if not source or source.user_id != user.id:
        raise HTTPException(status_code=404, detail="리서치 소스를 찾을 수 없습니다.")
    source.is_active = False
    return {"status": "deleted"}


@router.post("/run")
async def run_now(background_tasks: BackgroundTasks, user: User = Depends(get_current_user)):
    background_tasks.add_task(run_research_for_user, str(user.id))
    return {"status": "collecting"}


@router.get("/latest")
async def latest_research(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    run_result = await db.execute(
        select(ResearchRun)
        .where(ResearchRun.user_id == user.id)
        .order_by(ResearchRun.started_at.desc())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()
    if not run:
        return {"run": None, "proposals": []}

    proposal_result = await db.execute(
        select(TopicProposal, ContentSession)
        .outerjoin(ContentSession, ContentSession.id == TopicProposal.session_id)
        .where(TopicProposal.run_id == run.id, TopicProposal.user_id == user.id)
        .order_by(TopicProposal.created_at.asc())
    )
    proposal_rows = proposal_result.fetchall()
    return {
        "run": {
            "id": str(run.id),
            "status": run.status,
            "item_count": run.item_count,
            "notification_sent": run.notification_sent,
            "error_message": run.error_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "proposals": [
            {
                "id": str(proposal.id),
                "title": proposal.title,
                "message": proposal.message,
                "rationale": proposal.rationale,
                "evidence": proposal.evidence or [],
                "channels": proposal.channels or list(SUPPORTED_CHANNELS),
                "status": proposal.status,
                "session_id": str(proposal.session_id) if proposal.session_id else None,
                "session_status": session.status if session else None,
                "session_created_at": session.created_at.isoformat() if session and session.created_at else None,
                "generation_current_channel": session.generation_current_channel if session else None,
                "generation_done": session.generation_done if session else 0,
                "generation_total": session.generation_total if session else 0,
                "error_message": session.error_message if session else "",
            }
            for proposal, session in proposal_rows
        ],
    }


@router.post("/proposals/{proposal_id}/select")
async def select_proposal(
    proposal_id: str,
    body: ProposalSelect,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    invalid_channels = [ch for ch in body.channels if ch not in SUPPORTED_CHANNELS]
    if invalid_channels:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 채널입니다: {', '.join(invalid_channels)}")
    if not body.channels:
        raise HTTPException(status_code=400, detail="생성할 채널을 1개 이상 선택해 주세요.")

    result = await db.execute(select(TopicProposal).where(TopicProposal.id == parse_uuid(proposal_id, "proposal_id")))
    proposal = result.scalar_one_or_none()
    if not proposal or proposal.user_id != user.id:
        raise HTTPException(status_code=404, detail="주제 제안을 찾을 수 없습니다.")
    if proposal.status in {"generating", "generated", "cancel_requested"} and proposal.session_id:
        return {"status": proposal.status, "session_id": str(proposal.session_id)}

    selected_topic = {
        "title": proposal.title,
        "message": proposal.message,
        "rationale": proposal.rationale,
        "emotion": "퇴직과 수입에 대한 현실적 불안",
        "channel": "blog",
        "channels": body.channels,
        "evidence": proposal.evidence or [],
    }
    evidence_memo = "\n".join([
        f"- {item.get('title', '')}: {item.get('url', '')} {item.get('note', '')}"
        for item in (proposal.evidence or [])
    ])
    session = ContentSession(
        user_id=user.id,
        input_keyword=proposal.title,
        input_emotion=selected_topic["emotion"],
        input_memo=evidence_memo,
        input_exclude="수집 자료에 없는 수치, 사례, 확정적 수익 표현",
        topic_candidates=[selected_topic],
        selected_topic=selected_topic,
        status="generating",
        error_message=None,
        generation_current_channel="source_package",
        generation_done=0,
        generation_total=len(body.channels),
    )
    db.add(session)
    proposal.status = "generating"
    await db.flush()
    proposal.session_id = session.id
    await db.commit()

    from sessions import _run_generation
    background_tasks.add_task(
        _run_generation,
        str(user.id),
        str(session.id),
        selected_topic,
        body.channels,
        selected_topic["emotion"],
        evidence_memo,
        "수집 자료에 없는 수치, 사례, 확정적 수익 표현",
    )
    return {"status": "generating", "session_id": str(session.id)}
