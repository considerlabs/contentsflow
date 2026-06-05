# ============================================
# ContentFlow — 오케스트레이터 + 에이전트
# ============================================
import json
import time
import httpx
from pathlib import Path

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.6:35b-a3b"


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

# ── 지식 베이스 로드 ──────────────────────────
def load_knowledge(user_id: str, persona_md: str, style_md: str, topic_keywords: list) -> str:
    topic_section = "\n".join([f"- {k}" for k in topic_keywords])
    return f"""
## persona.md
{persona_md}

## style.md
{style_md}

## 등록된 키워드 목록
{topic_section}
""".strip()


# ── Ollama 호출 ──────────────────────────────
async def call_llm(prompt: str, system: str = "", num_predict: int = 8192) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": num_predict},
    }
    async with httpx.AsyncClient(timeout=300) as client:
        res = await client.post(OLLAMA_URL, json=payload)
        res.raise_for_status()
        data = res.json()
        # qwen3.6 thinking 모델: response가 비면 thinking 필드 fallback
        return (data.get("response") or data.get("thinking") or "").strip()


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
    try:
        start = raw.find("[")
        end   = raw.rfind("]") + 1
        return json.loads(raw[start:end])
    except Exception:
        return [{"title": raw[:100], "message": "", "emotion": "", "channel": "blog"}]


# ── Step 2: 채널별 초안 생성 ──────────────────
async def generate_draft(
    knowledge: str,
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
- 출력 형식: 마크다운
""",
        "newsletter": """
뉴스레터 초안을 작성하라.
- 길이: 읽기 5분 이내
- 구조: 오프닝(에디터 경험 연결) → AI 소식 3건 → 따라해보기 → 마무리 CTA
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
숏폼 대본을 작성하라.
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
확정된 주제: {selected_topic.get('title')}
핵심 메시지: {selected_topic.get('message')}
타겟 감정: {input_emotion}
경험 메모: {input_memo or "없음"}

{channel_instructions.get(channel_type, "")}

위 지시에 따라 초안을 작성하라.
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
        "llm_model":     OLLAMA_MODEL,
        "generation_ms": elapsed
    }


# ── Step 3: QC 자체 검토 ─────────────────────
async def run_qc(body_md: str, channel_type: str) -> dict:
    checks = {
        "금지 표현 없음": all(
            x not in body_md for x in ["쉽습니다", "간단합니다", "누구나 할 수"]
        ),
        "구체적 수치 포함": any(
            c.isdigit() for c in body_md
        ),
        "CTA 포함": any(
            kw in body_md for kw in ["구독", "링크", "더 알고 싶"]
        ),
        "분량 기준 충족": (
            len(body_md.replace(" ", "").replace("\n", "")) >= 800
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
    channels: list[str]
) -> list[dict]:
    knowledge = load_knowledge("", persona_md, style_md, topic_keywords)
    results   = []

    for ch in channels:
        draft  = await generate_draft(knowledge, selected_topic, ch, input_emotion, input_memo)
        qc     = await run_qc(draft["body_md"], ch)
        draft["qc_passed"]  = qc["passed"]
        draft["qc_results"] = qc["results"]
        results.append(draft)

    return results
