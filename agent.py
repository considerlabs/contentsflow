# ============================================
# ContentFlow — 오케스트레이터 + 에이전트
# ============================================
import json
import os
import re
import time
import httpx

OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "qwen3.6:35b-a3b")
LLM_PROVIDER   = os.getenv("LLM_PROVIDER", "ollama")   # ollama | claude | gemini
CLAUDE_MODEL   = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SUPPORTED_CHANNELS = ("blog", "newsletter", "youtube", "shortform")


_SECTION_LABELS = ["마크다운", "html", "스크립트", "대본", "숏폼 대본", "유튜브 스크립트",
                   "버전", "오프닝", "본론"]

def _extract_title(body_md: str, fallback: str = "") -> str:
    for line in body_md.splitlines():
        if not line.startswith("# "):
            continue
        title = line[2:].strip()
        # "제목: " 접두어 제거
        if title.lower().startswith("제목:"):
            title = title[3:].strip().lstrip(": ").strip()
        # 이모지 접두어 제거
        title = title.lstrip("📝📧🎬📱✦⏱️🎤#").strip()
        # 섹션 레이블 건너뜀 (실제 제목 아님)
        lower = title.lower()
        if any(p in lower for p in _SECTION_LABELS):
            continue
        if len(title) > 5:
            return title
    return fallback


def _extract_json(raw: str, fallback):
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass

    starts = [i for i in [raw.find("{"), raw.find("[")] if i >= 0]
    if not starts:
        return fallback
    start = min(starts)
    end = max(raw.rfind("}"), raw.rfind("]")) + 1
    if end <= start:
        return fallback
    try:
        return json.loads(raw[start:end])
    except Exception:
        return fallback


def _extract_newsletter_html(body_md: str) -> str:
    match = re.search(r"```html\s*(.*?)\s*```", body_md or "", flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    lower = (body_md or "").lower()
    start = lower.find("<html")
    if start < 0:
        start = lower.find("<table")
    if start < 0:
        start = lower.find("<body")
    return body_md[start:].strip() if start >= 0 else ""


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=_json_default)

# ── 지식 베이스 로드 ──────────────────────────
def load_knowledge(user_id: str, persona_md: str, style_md: str, topic_keywords: list,
                   topic_md: str = "") -> str:
    topic_section = "\n".join([f"- {k}" for k in topic_keywords])
    parts = [
        f"## persona.md\n{persona_md}",
        f"## style.md\n{style_md}",
    ]
    if topic_md:
        parts.append(f"## topic.md\n{topic_md}")
    if topic_section:
        parts.append(f"## 등록된 키워드 목록\n{topic_section}")
    return "\n\n".join(parts)


# ── LLM 호출 ─────────────────────────────────
async def call_llm(prompt: str, system: str = "", num_predict: int = 8192) -> str:
    if LLM_PROVIDER == "claude":
        return await _call_claude(prompt, system)
    elif LLM_PROVIDER == "gemini":
        return await _call_gemini(prompt, system)
    else:
        return await _call_ollama(prompt, system, num_predict)


async def _call_ollama(prompt: str, system: str = "", num_predict: int = 8192) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": num_predict},
    }
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post(OLLAMA_URL, json=payload)
            res.raise_for_status()
            data = res.json()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Ollama에 연결할 수 없습니다. Ollama 서버를 실행하고 {OLLAMA_MODEL} 모델을 준비해 주세요."
        ) from exc
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        raise RuntimeError(
            f"Ollama 호출 실패: HTTP {exc.response.status_code}. 모델명({OLLAMA_MODEL})과 Ollama 상태를 확인해 주세요. {body}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("Ollama 응답 시간이 너무 깁니다. 모델 로딩 상태와 시스템 자원을 확인해 주세요.") from exc

    # qwen3.6 thinking 모델: response가 비면 thinking 필드 fallback
    text = (data.get("response") or data.get("thinking") or "").strip()
    if not text:
        raise RuntimeError("Ollama 응답이 비어 있습니다. 모델 응답 형식과 실행 상태를 확인해 주세요.")
    return text


async def _call_claude(prompt: str, system: str = "") -> str:
    headers = {
        "x-api-key": CLAUDE_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        raise RuntimeError(f"Claude API 호출 실패: HTTP {exc.response.status_code}. {body}") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("Claude API 응답 시간 초과.") from exc
    return data["content"][0]["text"].strip()


async def _call_gemini(prompt: str, system: str = "") -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "알겠습니다."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    payload = {"contents": contents, "generationConfig": {"maxOutputTokens": 8192}}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            res = await client.post(url, params={"key": GEMINI_API_KEY}, json=payload)
            res.raise_for_status()
            data = res.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        raise RuntimeError(f"Gemini API 호출 실패: HTTP {exc.response.status_code}. {body}") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError("Gemini API 응답 시간 초과.") from exc
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Step 1: 주제 후보 3개 생성 ────────────────
async def generate_topic_candidates(
    knowledge: str,
    input_keyword: str,
    input_emotion: str,
    input_exclude: str
) -> list[dict]:
    prompt = f"""
{knowledge}

---
사용자 입력:
- 키워드: {input_keyword}
- 타겟 감정: {input_emotion}
- 제외 사항: {input_exclude or "없음"}

위 정보를 바탕으로 콘텐츠 주제 후보 3개를 제안하라.
반드시 아래 JSON 형식으로만 출력하라. 다른 텍스트 없이 JSON만:

[
  {{
    "title": "제목 안",
    "message": "핵심 메시지 한 문장",
    "emotion": "독자 반응 예상",
    "channel": "가장 적합한 채널 (blog|newsletter|youtube|shortform)"
  }},
  ...
]
"""
    raw = await call_llm(prompt)
    data = _extract_json(raw, fallback=None)
    if isinstance(data, list) and data:
        return data[:3]
    return [{"title": raw[:100], "message": "", "emotion": "", "channel": "blog"}]


async def generate_researched_topic_proposals(
    knowledge: str,
    research_items: list[dict],
    count: int = 5,
) -> list[dict]:
    compact_items = []
    for item in research_items[:30]:
        published_at = item.get("published_at", "")
        if hasattr(published_at, "isoformat"):
            published_at = published_at.isoformat()
        compact_items.append({
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "url": item.get("url", ""),
            "source": item.get("source", ""),
            "published_at": published_at,
        })

    prompt = f"""
{knowledge}

---
오늘 새벽 수집한 자료:
{_safe_json(compact_items)}

위 자료만 근거로 오늘 만들 콘텐츠 주제 {count}개를 제안하라.

원칙:
- 50~60대 재직자, 퇴직 불안, AI 기반 부수입 파이프라인이라는 사용자 페르소나에 맞출 것
- 수집 자료에 없는 사실, 수치, 사례를 만들지 말 것
- 블로그 원문 허브로 발행한 뒤 뉴스레터·유튜브·인스타그램으로 재활용하기 좋은 주제를 우선할 것
- 각 주제는 왜 지금 써야 하는지와 근거 자료 URL을 포함할 것

반드시 아래 JSON 형식으로만 출력하라. 다른 텍스트 없이 JSON만:

[
  {{
    "title": "주제 제목",
    "message": "핵심 메시지 한 문장",
    "rationale": "이 주제가 오늘 유효한 이유",
    "emotion": "독자가 느낄 감정",
    "channel": "blog",
    "channels": ["blog", "newsletter", "youtube", "shortform"],
    "evidence": [
      {{"title": "근거 자료 제목", "url": "https://...", "note": "이 자료를 어떻게 활용할지"}}
    ]
  }}
]
"""
    raw = await call_llm(prompt, num_predict=8192)
    data = _extract_json(raw, fallback=None)
    if isinstance(data, list) and data:
        proposals = []
        for item in data[:count]:
            if not isinstance(item, dict):
                continue
            item.setdefault("channels", list(SUPPORTED_CHANNELS))
            item.setdefault("channel", "blog")
            item.setdefault("evidence", [])
            proposals.append(item)
        if proposals:
            return proposals

    fallback_items = compact_items[:count]
    return [
        {
            "title": item.get("title") or f"오늘의 리서치 주제 {idx + 1}",
            "message": item.get("summary", "")[:160],
            "rationale": "수집 자료를 직접 근거로 작성할 수 있는 주제입니다.",
            "emotion": "퇴직과 수입에 대한 현실적 불안",
            "channel": "blog",
            "channels": list(SUPPORTED_CHANNELS),
            "evidence": [{"title": item.get("title", ""), "url": item.get("url", ""), "note": item.get("summary", "")[:120]}],
        }
        for idx, item in enumerate(fallback_items)
    ]


async def generate_source_package(
    knowledge: str,
    selected_topic: dict,
    input_emotion: str,
    input_memo: str,
    input_exclude: str
) -> dict:
    prompt = f"""
{knowledge}

---
확정된 주제:
- 제목: {selected_topic.get('title')}
- 핵심 메시지: {selected_topic.get('message')}
- 근거 자료: {_safe_json(selected_topic.get('evidence', []))}
- 타겟 감정: {input_emotion}
- 경험 메모: {input_memo or "없음"}
- 제외 사항: {input_exclude or "없음"}

블로그, 뉴스레터, 유튜브, 인스타그램 숏폼에 공통으로 쓸 원본 기획 패키지를 작성하라.
반드시 아래 JSON 형식으로만 출력하라. 다른 텍스트 없이 JSON만:

{{
  "core_angle": "모든 채널이 공유할 한 문장 관점",
  "reader_problem": "독자가 지금 겪는 구체적 문제",
  "promise": "콘텐츠가 독자에게 주는 실질적 약속",
  "proof_points": ["검증된 경험 또는 근거 1", "검증된 경험 또는 근거 2"],
  "outline": ["도입", "공감", "경험", "실행 단계", "CTA"],
  "forbidden_claims": ["말하면 안 되는 과장 또는 미검증 주장"],
  "cta": "자연스러운 다음 행동",
  "channel_strategy": {{
    "blog": "검색 유입용 각도",
    "newsletter": "관계 유지용 각도",
    "youtube": "시청 지속용 각도",
    "shortform": "인스타그램 릴스/쇼츠용 각도"
  }}
}}

검증되지 않은 수치나 사례를 만들지 말라.
근거 자료가 제공된 경우 해당 자료의 주장 범위 안에서만 활용하라.
"""
    raw = await call_llm(prompt, num_predict=4096)
    fallback = {
        "core_angle": selected_topic.get("message") or selected_topic.get("title", ""),
        "reader_problem": input_emotion,
        "promise": selected_topic.get("message") or "",
        "proof_points": [input_memo] if input_memo else [],
        "outline": ["공감", "경험", "실행 단계", "오늘 할 일", "CTA"],
        "forbidden_claims": [input_exclude] if input_exclude else [],
        "cta": "다음 콘텐츠에서 실행 과정을 이어서 확인하도록 안내",
        "channel_strategy": {},
    }
    data = _extract_json(raw, fallback=fallback)
    return data if isinstance(data, dict) else fallback


# ── Step 2: 채널별 초안 생성 ──────────────────
async def generate_draft(
    knowledge: str,
    source_package: dict,
    selected_topic: dict,
    channel_type: str,
    input_emotion: str,
    input_memo: str
) -> dict:
    channel_instructions = {
        "blog": """
블로그 포스트 초안을 작성하라.
- 길이: 1,200~1,500자
- 구조: 후킹 도입 → 문제 공감 → 브라이언 경험 → 단계별 해결책(3~5단계) → 오늘 당장 할 수 있는 것 1가지 → CTA
- SEO: 제목, 메타 설명(80자 이내), H2 소제목 3~5개 포함
- 목표: 검색 유입 후 뉴스레터/유튜브/인스타그램으로 확장 가능한 원문 허브
- 출력 형식: 마크다운
""",
        "newsletter": """
뉴스레터 초안을 작성하라.
- 길이: 읽기 5분 이내
- 구조: 오프닝(에디터 경험 연결) → 이번 주 핵심 관점 → 따라해보기 → 블로그/유튜브/인스타그램 연결 CTA
- 해요체, 짧은 문장(40자 이내), "우리" 연대감
- 출력 형식: 마크다운 + HTML 두 버전
""",
        "youtube": """
유튜브 스크립트와 썸네일 문구를 작성하라.
- 분량: 7~10분 (A4 3~4페이지)
- 구조: 후킹(30초) → 본론 3파트(각 2분) → 요약+CTA(1분)
- 화면 지시: [화면: ~] 태그 포함
- 썸네일 문구 3개 안: 숫자+공감 키워드 포함, 15자 이내
- 출력 형식: 마크다운
""",
        "shortform": """
인스타그램 릴스/쇼츠용 숏폼 대본을 작성하라.
- 길이: 60초 이내
- 구조: 후킹(5초) → 핵심 3가지(각 15초) → CTA(5초)
- 자막 형식: 한 줄 15자 이내
- [자막], [강조] 태그 포함
- 출력 형식: 마크다운
"""
    }

    prompt = f"""
{knowledge}

---
원본 기획 패키지:
{_safe_json(source_package)}

확정된 주제: {selected_topic.get('title')}
핵심 메시지: {selected_topic.get('message')}
타겟 감정: {input_emotion}
경험 메모: {input_memo or "없음"}

{channel_instructions.get(channel_type, "")}

위 지시에 따라 초안을 작성하라.
모든 채널은 같은 관점과 근거를 공유하되, 채널별 형식과 CTA만 다르게 변환하라.
절대 금지: 검증되지 않은 수치 창작, "쉽습니다/간단합니다/누구나" 표현
"""
    token_budget = 16384 if channel_type == "youtube" else 8192
    start_ms = int(time.time() * 1000)
    body_md  = await call_llm(prompt, num_predict=token_budget)
    elapsed  = int(time.time() * 1000) - start_ms

    return {
        "channel_type":  channel_type,
        "title":         _extract_title(body_md, fallback=selected_topic.get("title", "")),
        "body_md":       body_md,
        "body_html":     _extract_newsletter_html(body_md) if channel_type == "newsletter" else "",
        "source_package": source_package,
        "llm_model":     OLLAMA_MODEL,
        "generation_ms": elapsed
    }


# ── Step 3: QC 자체 검토 ─────────────────────
async def run_qc(body_md: str, channel_type: str) -> dict:
    compact_len = len((body_md or "").replace(" ", "").replace("\n", ""))
    checks = {
        "금지 표현 없음": all(
            x not in body_md for x in ["쉽습니다", "간단합니다", "누구나 할 수", "무조건", "보장"]
        ),
        "구체적 수치 포함": any(
            c.isdigit() for c in body_md
        ),
        "CTA 포함": any(
            kw in body_md for kw in ["구독", "링크", "댓글", "저장", "더 알고 싶", "확인"]
        ),
        "독자 문제 명시": any(
            kw in body_md for kw in ["불안", "걱정", "고민", "막막", "퇴직", "수입"]
        ),
        "실행 단계 포함": any(
            kw in body_md for kw in ["1단계", "2단계", "Step", "오늘", "체크리스트", "따라"]
        ),
        "채널 포맷 준수": (
            ("[자막]" in body_md if channel_type == "shortform" else True)
            and ("썸네일" in body_md if channel_type == "youtube" else True)
            and (("html" in body_md.lower() or "<" in body_md) if channel_type == "newsletter" else True)
        ),
        "분량 기준 충족": (
            compact_len >= (300 if channel_type == "shortform" else 800)
        ),
    }
    passed = all(checks.values())
    return {"passed": passed, "results": checks}


# ── 전체 파이프라인 실행 ──────────────────────
async def run_pipeline(
    persona_md: str,
    style_md: str,
    topic_keywords: list,
    input_keyword: str,
    input_emotion: str,
    input_memo: str,
    input_exclude: str,
    selected_topic: dict,
    channels: list[str],
    topic_md: str = ""
) -> list[dict]:
    knowledge = load_knowledge("", persona_md, style_md, topic_keywords, topic_md=topic_md)
    source_package = await generate_source_package(
        knowledge, selected_topic, input_emotion, input_memo, input_exclude
    )
    results   = []

    for ch in channels:
        draft  = await generate_draft(knowledge, source_package, selected_topic, ch, input_emotion, input_memo)
        qc     = await run_qc(draft["body_md"], ch)
        draft["qc_passed"]  = qc["passed"]
        draft["qc_results"] = qc["results"]
        results.append(draft)

    return results
