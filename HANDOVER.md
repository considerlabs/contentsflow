# ContentFlow 작업 인수인계

## 작업 일자
2026-06-06 (최초)  
2026-06-06 (버그 수정 — 모달 버튼 클리핑)  
2026-06-09 (자동 콘텐츠 생성 UX 개선 + RSS 파서 교체)

---

## 1. 신규 파일

### `settings_api.py`
LLM 설정 영구 저장 API 모듈.

- `GET /api/settings` — 현재 LLM 설정 조회 (API 키는 has_*_key 불린으로만 반환)
- `PUT /api/settings` — LLM 제공자·모델·API 키 변경
- `apply_saved_settings()` — 서버 시작 시 `settings.json`에서 설정 복원 (lifespan 훅에서 호출)
- `settings.json` — 설정 영구 저장 파일 (gitignore 적용, API 키 포함)

### `frontend/draft-modal.js`
검수 모달 공통 컴포넌트. dashboard / generate / history 세 페이지에서 공유.

- 자체 CSS(`.dm-*` 접두사)·HTML을 DOM에 주입하는 IIFE
- `window.openDraftModal(id, chType, title, { onReview })` — 모달 열기
- `window.closeDraftModal()` — 모달 닫기
- 내부적으로 localStorage 토큰 읽어 API 호출 (페이지 auth 함수에 의존하지 않음)
- `status === 'review'`인 초안에서만 검수 영역(수정 요청 textarea + 3개 버튼) 표시
- **버그 수정**: `.dm-footer padding-bottom: 15px → 20px` — `border-radius:14px` + `overflow:hidden` 조합이 하단 모서리 14px 이내 콘텐츠를 클리핑하는 현상 수정

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
- `proposals` API 응답에 `session_created_at` 필드 추가 (자동 생성 타이머 기준 시각)
- **RSS 파서 교체**: `xml.etree.ElementTree` (strict) → `feedparser 6.0.11`
  - 불량 XML 피드(unescaped `&`, 잘못된 인코딩, 비표준 포맷)를 자동 복구 파싱
  - 응답이 HTML 페이지인 경우 명확한 오류 메시지 제공 ("RSS 피드 URL이 HTML 페이지를 반환했습니다")
  - 제거된 dead code: `_local_name`, `_first_text`, `_first_link`, `_parse_date` 함수, `ElementTree` 임포트

### `requirements.txt`
- `feedparser==6.0.11` 추가

### `frontend/auto_content.html`
**자동 콘텐츠 생성 페이지 UX 개선**

#### 진행 상태 표시 개선
- 생성 단계별 설명 레이블 (`STEP_DESC` 상수):
  - `source_package` → "공통 기획 패키지 준비 중"
  - `blog` → "블로그 초안 작성 중"
  - `newsletter` → "뉴스레터 초안 작성 중"
  - `youtube` → "유튜브 스크립트 작성 중"
  - `shortform` → "숏폼 대본 작성 중"
- 진행 중 레이블을 파란색 굵게 표시, 완료 시 회색으로 변경
- `X / N 채널 완료` 카운트 별도 표시

#### 경과 시간 타이머 추가 (3개 지점)
| 상태 | 시작 기준 |
|---|---|
| "수동 수집" 버튼 클릭 직후 | 클라이언트 클릭 시각 (`Date.now()`) |
| 수집 중 (`collecting`) 폴링 시 | 서버의 `run.started_at` |
| 채널 초안 생성 중 | 세션 생성 시각 (`session_created_at`) |

- 모든 타이머는 `data-session-start` 어트리뷰트 + `setInterval` 1초 갱신

#### 리서치 실패 즉시 표시
- `silent=true` 폴링 중 `run.status === 'failed'`가 되어도 즉시 에러박스 표시
- 기존: silent 조건으로 폴링 시 실패가 숨겨져 다른 페이지 갔다 돌아올 때까지 인지 불가
- `stopElapsedTimer()` 호출로 타이머 정리

#### 페이지 이동 후 복귀 시 에러 방지
- `pagehide` 이벤트: 타이머·폴링 정리
- `pageshow` 이벤트: bfcache 복원(`event.persisted`) 시 상태 초기화 후 재로드
- `loadResearch` catch: AbortError / "Failed to fetch"는 에러 메시지 미표시

### `frontend/dashboard.html` / `frontend/auto_content.html` / `frontend/settings.html`
- 사이드바 로고 → `/dashboard` 링크
- 설정 링크 → `/settings#channels`, `/settings#research-sources` 해시 연동

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
| 발행 채널 연동 | 미구현 | 승인 시 `publish_failed`로 떨어짐. 티스토리·스티비·구글 드라이브·인스타그램 API 연동 필요 |
| settings.json gitignore | ✅ 완료 | `.gitignore`에 추가됨 |
| Claude/Gemini LLM 실사용 테스트 | 미완료 | API 키 입력 후 실제 생성 테스트 필요 |
| 대시보드 초안 삭제 기능 | 미이식 | 공통 모달 전환 과정에서 "빈 초안 삭제" 버튼 로직 미이식 |
| feedparser==6.0.11 | ✅ 완료 | `pip install feedparser==6.0.11` 필요 |

---

## 5. 리서치 소스 관련 주의사항

- RSS URL이 HTML 페이지를 반환하면 "RSS 피드 URL이 HTML 페이지를 반환했습니다" 오류
- `sidehustleschool.com/feed/` — 현재 404, 유효한 RSS URL로 교체 필요
- Ollama 서버가 실행 중이어야 리서치/생성 작동 (`ollama serve`)

---

## 6. 로컬 실행

```bash
cd /Users/guyskim/contentsflow
pip install -r requirements.txt   # feedparser 신규 추가
python3 main.py
# http://localhost:8000/dashboard
```

서버 시작 시 `settings.json`이 있으면 LLM 설정 자동 복원.  
`--reload` 옵션 사용 시 파일 변경 때마다 서버 재시작 → 진행 중인 백그라운드 작업 중단 주의.
