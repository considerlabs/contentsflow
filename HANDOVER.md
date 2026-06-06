# ContentFlow 작업 인수인계

## 작업 일자
2026-06-06

---

## 1. 신규 파일

### `settings_api.py`
LLM 설정 영구 저장 API 모듈.

- `GET /api/settings/llm` — 현재 LLM 설정 조회 (API 키는 has_*_key 불린으로만 반환)
- `PUT /api/settings/llm` — LLM 제공자·모델·API 키 변경
- `apply_saved_settings()` — 서버 시작 시 `settings.json`에서 설정 복원 (lifespan 훅에서 호출)
- `settings.json` — 설정 영구 저장 파일 (gitignore 권장, API 키 포함)

### `frontend/draft-modal.js`
검수 모달 공통 컴포넌트. dashboard / generate / history 세 페이지에서 공유.

- 자체 CSS(`.dm-*` 접두사)·HTML을 DOM에 주입하는 IIFE
- `window.openDraftModal(id, chType, title, { onReview })` — 모달 열기
- `window.closeDraftModal()` — 모달 닫기
- 내부적으로 localStorage 토큰 읽어 API 호출 (페이지 auth 함수에 의존하지 않음)
- `status === 'review'`인 초안에서만 검수 영역(수정 요청 textarea + 3개 버튼) 표시

---

## 2. 변경 파일

### `agent.py`
**다중 LLM 제공자 지원 추가**

| 모듈 변수 | 설명 |
|---|---|
| `LLM_PROVIDER` | `ollama` \| `claude` \| `gemini` (기본: `ollama`) |
| `CLAUDE_MODEL` | 기본: `claude-sonnet-4-6` |
| `CLAUDE_API_KEY` | Claude API 키 |
| `GEMINI_MODEL` | 기본: `gemini-2.0-flash` |
| `GEMINI_API_KEY` | Gemini API 키 |

- `call_llm()` → 내부적으로 `LLM_PROVIDER` 분기 후 `_call_ollama()` / `_call_claude()` / `_call_gemini()` 호출
- `_call_claude()` — Anthropic Messages API (`https://api.anthropic.com/v1/messages`)
- `_call_gemini()` — Google Generative Language API
- 설정은 `settings_api.apply_saved_settings()`가 서버 시작 시 모듈 변수에 주입

### `main.py`
- `settings_api` 라우터 등록 (`/api/settings`)
- lifespan에서 `settings_api.apply_saved_settings()` 호출

### `research.py`
- proposals API 응답에 `session_created_at` 필드 추가 (자동 생성 타이머 기준 시각)

### `frontend/dashboard.html`
**UI 변경**

- 사이드바 로고 → `/dashboard` 링크, 대시보드 nav 항목 제거
- "작업 진입점" 패널 제거
- 자동 컨텐츠 생성 현황 텍스트 overflow 수정 (`overflow-wrap`, `word-break`)
- 검수 모달 → `draft-modal.js` 공통 모달로 교체 (내부 HTML/CSS/JS 제거)
- 리서치 모달 footer 간소화 (닫기 + 생성 버튼만, "선택가능" 문구 제거)

### `frontend/auto_content.html`
**UI 변경**

- 사이드바 로고 → `/dashboard` 링크, 대시보드 nav 항목 제거
- 토픽 카드 버튼 클리핑 수정 (`min-height:180px` 제거, `align-items:start` 제거)
- **중지 버튼**: 생성 중 → "중지", 중단 요청됨 → disabled "중단 요청됨" 표시
- **다시 생성**: cancel_requested / cancelled 상태에서 "다시 생성" 버튼 표시 (기존 세션 삭제 후 재시작)
- **진행 타이머**: 생성 중(`generating`) 및 중단 요청(`cancel_requested`) 상태에서만 경과 시간 표시. 완료 카드에는 미표시
- 타이머 구현: `sessionStartTimes` 맵 + `setInterval` 1초 갱신, `session_created_at` 서버 기준 시각 사용

### `frontend/settings.html`
**UI 변경**

- 사이드바 로고 → `/dashboard` 링크, 대시보드 nav 항목 제거
- 탭 순서 수정 (리서치소스 탭 3번, LLM설정 탭 4번 — DOM 순서와 탭 인덱스 일치)
- **LLM 설정 탭 다중 제공자 지원**:
  - 제공자 선택 버튼 (Ollama / Claude API / Gemini API)
  - Ollama: 모델 드롭다운·직접 입력 + 서버 URL
  - Claude API: 모델 선택 + API 키 (password 타입)
  - Gemini API: 모델 선택 + API 키 (password 타입)

### `frontend/generate.html`
**UI 변경**

- 사이드바 로고 → `/dashboard` 링크, 대시보드 nav 항목 제거
- 브라우저 탭 타이틀: `콘텐츠 생성`
- 검수대기 카드 클릭 → `draft-modal.js` 공통 모달 (내부 모달 코드 제거)
- shortform ch-badge 색상: `#e0f2fe / #0369a1` (파란색, 타 페이지와 통일)

### `frontend/history.html`
**UI 변경**

- 사이드바 로고 → `/dashboard` 링크, 대시보드 nav 항목 제거
- 브라우저 탭 타이틀: `콘텐츠 이력`
- 이력 행 클릭 → `draft-modal.js` 공통 모달 (내부 모달 코드 제거)
- shortform ch-badge 색상: `#e0f2fe / #0369a1` (파란색, 타 페이지와 통일)
- `alert()` → toast 메시지로 교체

---

## 3. 검수(Review) 기능 흐름

```
초안 상태: review
    ↓ 카드/행 클릭
openDraftModal() [draft-modal.js]
    ↓ GET /api/drafts/{id}
    status=review → 검수 영역 표시
    ↓ 버튼 클릭
POST /api/sessions/drafts/{id}/review
    body: { action: "approved"|"revision"|"rejected", memo: string|null }
    ↓
    approved  → publish_failed (발행 채널 미연동 상태)
    revision  → revision
    rejected  → rejected
    ↓
onReview 콜백 → 목록 새로고침
```

---

## 4. 미완성 / 향후 과제

| 항목 | 상태 | 비고 |
|---|---|---|
| 발행 채널 연동 | 미구현 | 승인 시 `publish_failed`로 떨어짐. 실제 블로그/뉴스레터 발행 API 연동 필요 |
| settings.json gitignore | 권장 | API 키 포함 파일, 현재 미처리 |
| Claude/Gemini LLM 실사용 테스트 | 미완료 | API 키 입력 후 실제 생성 테스트 필요 |
| 대시보드 초안 삭제 기능 | 제거됨 | 공통 모달 전환 과정에서 "빈 초안 삭제" 버튼 로직 미이식 |

---

## 5. 로컬 실행

```bash
cd /Users/guyskim/contentsflow
uvicorn main:app --reload
# http://localhost:8000/dashboard
```

서버 시작 시 `settings.json`이 있으면 LLM 설정 자동 복원.
