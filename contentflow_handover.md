# ContentFlow 인수인계 문서

> 작성일: 2026-06-06  
> 최종 업데이트: 2026-06-06  
> 현재 버전 표기: v0.2.0  
> 핵심 LLM: Ollama `qwen3.6:35b-a3b`

---

## 1. 프로젝트 목적

ContentFlow는 블로그를 원문 허브로 삼고 뉴스레터, 유튜브, 인스타그램까지 확장하는 one source multi use 콘텐츠 운영 시스템이다.

사용자가 원하는 최종 운영 흐름은 다음과 같다.

1. 매일 새벽 등록된 RSS/사이트를 자동 검색하고 자료를 수집한다.
2. 수집 자료와 사용자 페르소나·키워드를 근거로 5개의 주제를 생성한다.
3. 이메일 또는 Notion으로 주제 알림을 보낸다.
4. 사용자가 주제 하나를 선택한다.
5. 로컬 LLM이 오래 걸리는 콘텐츠 생성을 백그라운드에서 수행한다.
6. 생성된 콘텐츠는 검수 대기 목록에 쌓인다.
7. 사용자는 출근 후 검수하고 블로그, 뉴스레터, 유튜브, 인스타그램 발행 흐름으로 넘긴다.

핵심 설계 원칙은 `대시보드는 모니터링`, `콘텐츠 생성은 별도 작업 화면`, `자동 콘텐츠 생성은 별도 작업 화면`이다.

---

## 2. 현재 화면 구조

### `/dashboard`

대시보드는 실행 화면이 아니라 상태 모니터링 화면이다.

현재 역할:

- 검수 대기, 승인·발행 완료, 수정 요청, 전체 콘텐츠 KPI 표시
- 자동 콘텐츠 생성 현황 요약
- 검수 대기 초안 목록 표시
- 채널별 누적 콘텐츠 수와 채널 역할 표시
- 수동 생성/자동 생성 화면으로 이동하는 진입점 제공

정리된 내용:

- 기존 `채널 활용` 영역은 검수 보드 안에 있어 역할이 불명확했고 화면도 좁아 깨질 수 있었다.
- 지금은 검수 보드에서 제거하고 `채널 현황` 별도 패널로 분리했다.
- 대시보드에서 수동 생성 팝업은 제거했다.
- 대시보드에서 자동 리서치 실행/주제 선택은 제거하고 `/auto-content`로 이동시켰다.

### `/generate`

수동 `콘텐츠 생성` 전용 화면이다.

현재 역할:

- 키워드, 타겟 감정, 제외할 내용 입력
- 주제 후보 3개 생성
- 주제 선택
- 블로그, 뉴스레터, 유튜브, 인스타그램 생성 채널 선택
- 백그라운드 생성 시작
- 생성 진행률, 현재 채널, 경과 시간 표시
- 생성 중단 및 세션 삭제
- 검수 대기 초안 목록 표시

생성 결과는 `content_drafts.status = review`로 저장되고 `/dashboard`, `/generate`, `/history`에서 확인된다.

### `/auto-content`

자동 콘텐츠 생성 전용 화면이다.

현재 역할:

- 최신 새벽 리서치 실행 상태 조회
- 수동 리서치 실행
- 주제 5개와 근거 자료 표시
- 주제 상세 보기
- 주제 선택 후 4채널 초안 생성 시작
- 주제별 진행률 표시
- 생성 중단 및 세션 삭제

이 화면이 이메일/Notion 알림에서 연결되는 주요 작업 화면이다.

### `/history`

생성된 전체 콘텐츠 이력 화면이다.

현재 역할:

- 채널별 필터
- 검색
- 상태 표시: review, approved, revision, rejected, published, publish_failed
- 출처 표시: `수동 생성`, `자동 리서치`
- 초안 상세 확인
- 승인·발행, 수정 요청, 반려

### `/settings`

설정 화면이다.

현재 역할:

- 카테고리·키워드 관리
- 발행 채널 설정
- 페르소나·스타일 수정
- 리서치 소스 등록·삭제

### `/onboarding`

최초 사용자 설정 화면이다.

현재 역할:

- 사용자 로그인/JWT 발급
- 페르소나 생성을 위한 질문 수집
- 기본 채널 선택
- 서버 기준 `onboarding_done` 저장

---

## 3. 주요 라우트

### 페이지 라우트

| 라우트 | 파일 | 역할 |
|---|---|---|
| `/` | redirect | `/dashboard`로 이동 |
| `/dashboard` | `frontend/dashboard.html` | 모니터링 대시보드 |
| `/generate` | `frontend/generate.html` | 수동 콘텐츠 생성 |
| `/auto-content` | `frontend/auto_content.html` | 자동 리서치 기반 콘텐츠 생성 |
| `/history` | `frontend/history.html` | 콘텐츠 이력·검수 |
| `/settings` | `frontend/settings.html` | 설정 |
| `/onboarding` | `frontend/onboarding.html` | 온보딩 |

### 주요 API

| API | 역할 |
|---|---|
| `POST /api/users/login` | 이메일 기반 로그인 및 JWT 발급 |
| `GET /api/users/me` | 현재 로그인 사용자 조회 |
| `POST /api/personas/generate` | 온보딩 답변 기반 페르소나 생성 |
| `GET /api/personas` | 사용자 페르소나 조회 |
| `PUT /api/personas/{persona_id}` | 페르소나 수정 |
| `GET/POST/DELETE /api/categories` | 카테고리 관리 |
| `GET/POST/DELETE /api/keywords` | 키워드 관리 |
| `GET/POST /api/channels` | 채널 설정 조회·저장 |
| `POST /api/sessions/` | 수동 생성용 세션 생성 및 주제 후보 생성 |
| `POST /api/sessions/{session_id}/generate` | 선택 주제 기반 채널별 초안 생성 |
| `GET /api/sessions/{session_id}` | 세션 진행 상태 조회 |
| `POST /api/sessions/{session_id}/cancel` | 생성 중단 요청 |
| `DELETE /api/sessions/{session_id}` | 세션 및 연결 초안 삭제 |
| `GET /api/drafts/pending` | 검수 대기 초안 목록 |
| `GET /api/drafts/published` | 이력 화면용 초안·발행 목록 |
| `GET /api/drafts/{draft_id}` | 초안 상세 |
| `DELETE /api/drafts/{draft_id}` | 초안 삭제 |
| `POST /api/sessions/drafts/{draft_id}/review` | 승인·수정 요청·반려 |
| `GET/POST/DELETE /api/research/sources` | 리서치 소스 관리 |
| `POST /api/research/run` | 수동 리서치 실행 |
| `GET /api/research/latest` | 최신 리서치/주제 제안 조회 |
| `POST /api/research/proposals/{proposal_id}/select` | 자동 리서치 주제 선택 및 생성 시작 |

---

## 4. 백엔드 구성

### `main.py`

- FastAPI 앱 생성
- CORS 설정
- 정적 프론트 파일 서빙
- API 라우터 등록
- 앱 시작 시 DB 테이블 생성 및 누락 컬럼 보강
- Notion poller와 새벽 리서치 스케줄러 실행

### `agent.py`

- Ollama 호출
- 기본 모델은 `qwen3.6:35b-a3b`
- 환경변수:
  - `OLLAMA_MODEL`
  - `OLLAMA_URL`
- 수동 주제 후보 3개 생성
- 리서치 기반 주제 5개 생성
- 원본 기획 패키지 생성
- 채널별 초안 생성
- QC 실행

### `sessions.py`

- 수동 생성 세션 생성
- 주제 선택 후 백그라운드 생성
- 생성 진행 상태 저장:
  - `generation_current_channel`
  - `generation_done`
  - `generation_total`
  - `error_message`
- 생성 중단 요청 처리
- 세션 삭제 처리
- 초안 승인·수정 요청·반려 처리
- 초안 생성 시 출처 메타 저장:
  - `source_type = manual | research`
  - `source_label = 수동 생성 | 자동 리서치`

### `research.py`

- RSS/Atom 수집
- 일반 사이트 HTML 수집
- 수집 자료 기반 주제 5개 생성
- 이메일 알림
- Notion 다이제스트 등록
- 매일 정해진 시간 자동 실행
- 주제 선택 시 `ContentSession`을 만들고 백그라운드 생성 시작
- 알림 링크는 `/auto-content`를 사용한다.

### `drafts.py`

- 검수 대기 목록, 이력 목록, 초안 상세 조회
- 출처 메타 반환
- 과거 데이터처럼 `ContentDraft.meta`에 출처가 없는 경우에도 `TopicProposal.session_id` 연결이 있으면 `자동 리서치`로 판별

### `publisher.py`

- 승인된 초안을 채널 설정에 맞춰 발행
- 블로그는 REST API 발행
- 뉴스레터는 API 발행
- 유튜브/인스타그램은 Webhook 또는 드라이브 저장 흐름
- 채널 설정이 없으면 실패 또는 승인 자산 보관으로 처리

### `notion.py`, `notion_poller.py`

- 초안 검수 큐를 Notion에 등록
- Notion 상태 변경을 감지해 승인·수정 요청 동기화
- 새벽 리서치 주제 다이제스트 등록

### `auth.py`, `users.py`

- 자체 HS256 JWT
- `Authorization: Bearer ...` 기반 인증
- 서버 기준 사용자와 온보딩 상태 관리
- user_id 위조 방지

---

## 5. DB 모델 요약

| 모델 | 역할 |
|---|---|
| `User` | 사용자, 온보딩 완료 여부 |
| `UserPersona` | 온보딩 답변, persona/style/topic 문서 |
| `Category` | 사용자 콘텐츠 카테고리 |
| `Keyword` | 카테고리별 키워드 |
| `ChannelConfig` | 채널별 API/Webhook/드라이브 설정 |
| `ContentSession` | 콘텐츠 생성 작업 단위 |
| `ContentDraft` | 채널별 생성 초안 |
| `ReviewLog` | 승인·수정 요청·반려 기록 |
| `ResearchSource` | RSS/사이트 수집 대상 |
| `ResearchRun` | 리서치 실행 기록 |
| `ResearchItem` | 수집된 개별 자료 |
| `TopicProposal` | 리서치 기반 주제 제안 |

중요 컬럼:

- `content_sessions.status`
  - `pending`, `generating`, `review`, `failed`, `cancel_requested`, `cancelled`
- `content_sessions.generation_current_channel`
  - `source_package`, `blog`, `newsletter`, `youtube`, `shortform`
- `content_drafts.status`
  - `review`, `approved`, `revision`, `rejected`, `published`, `publish_failed`
- `content_drafts.meta.source_type`
  - `manual`, `research`

---

## 6. 사용자 플로우

### 수동 콘텐츠 생성

1. `/generate` 접속
2. 키워드, 타겟 감정, 제외할 내용 입력
3. 주제 후보 3개 생성
4. 주제 선택
5. 생성 채널 선택
6. 4채널 초안 생성 시작
7. 생성 중 진행률 확인
8. 필요 시 중단 또는 세션 삭제
9. 완료 후 검수 대기 목록 또는 `/history`에서 확인

### 자동 콘텐츠 생성

1. 새벽 스케줄러가 리서치 실행
2. 수집 자료 기반 주제 5개 생성
3. 이메일/Notion 알림 발송
4. 사용자가 `/auto-content`에서 주제 확인
5. 주제 상세와 근거 검토
6. 주제 선택 후 4채널 초안 생성 시작
7. 주제 카드별 진행률 확인
8. 필요 시 중지 또는 삭제
9. 완료 후 `/dashboard`, `/history`에서 검수

### 검수 및 발행

1. `/dashboard` 또는 `/history`에서 검수 대기 초안 확인
2. 초안 상세 열기
3. 승인·발행, 수정 요청, 반려 중 선택
4. 승인 시 `publisher.py`가 채널 설정에 따라 발행 시도

---

## 7. 환경변수

대표 환경변수:

```env
DATABASE_URL=postgresql+asyncpg://...
JWT_SECRET=...
ENCRYPTION_KEY=...
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=qwen3.6:35b-a3b
APP_BASE_URL=http://localhost:8000
RESEARCH_DAILY_TIME=05:00
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
NOTION_API_KEY=
NOTION_DATABASE_ID=
```

운영 전 반드시 확인할 값:

- `JWT_SECRET`
- `ENCRYPTION_KEY`
- `DATABASE_URL`
- `OLLAMA_MODEL`
- `APP_BASE_URL`
- 리서치 알림을 쓸 경우 SMTP/Notion 값

---

## 8. 현재까지 반영된 주요 변경

### 인증/온보딩

- 클라이언트 저장 user_id 기준을 버리고 JWT와 `/api/users/me` 기준으로 변경
- 온보딩 완료 상태는 서버가 판단
- 페이지 진입 시 인증 실패 또는 온보딩 미완료면 `/onboarding`으로 이동

### 리서치/자동 생성

- 매일 새벽 자동 리서치 스케줄러 추가
- 수동 리서치 실행 추가
- 리서치 결과 주제 5개 생성
- 주제 선택 후 백그라운드 생성
- 진행 중인 주제별 상태 표시
- 생성 중단과 세션 삭제 지원
- datetime JSON 직렬화 오류 수정
- 리서치 상세를 팝업으로 확인 가능

### 생성 진행 관리

- 긴 LLM 작업을 백그라운드로 실행
- 채널별 생성 진행 상태 저장
- 일부 채널이 먼저 완성되면 초안이 검수 목록에 표시됨
- 수동 생성과 자동 리서치 생성 출처를 분리 표시

### 화면 구조

- `콘텐츠 생성`을 좌측 메뉴의 독립 화면으로 분리
- 기존 팝업 기반 생성 UI 제거
- `자동 콘텐츠 생성`을 좌측 메뉴의 독립 화면으로 분리
- 대시보드는 모니터링 중심으로 재구성
- 검수 보드 안의 `채널 활용` 제거
- `채널 현황`을 별도 패널로 분리
- 모든 주요 페이지 사이드바에 `콘텐츠 생성`, `자동 콘텐츠 생성` 메뉴 추가

---

## 9. 실행 및 검증

### 로컬 실행

```bash
python3 main.py
```

기본 서버:

```text
http://localhost:8000
```

주요 화면:

```text
http://localhost:8000/dashboard
http://localhost:8000/generate
http://localhost:8000/auto-content
http://localhost:8000/history
http://localhost:8000/settings
http://localhost:8000/onboarding
```

### 이번 작업 검증

수행한 검사:

```bash
python3 -c "import pathlib; [compile(pathlib.Path(f).read_text(), f, 'exec') for f in ['main.py','research.py','drafts.py','sessions.py']]; print('python syntax OK')"
```

```bash
node - <<'NODE'
const fs=require('fs');
for (const file of fs.readdirSync('frontend').filter(f=>f.endsWith('.html')).map(f=>'frontend/'+f)) {
  const html=fs.readFileSync(file,'utf8');
  const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]);
  for (const js of scripts) new Function(js);
  console.log(`${file}: OK`);
}
NODE
```

서버 응답 확인:

```bash
curl -s -L http://127.0.0.1:8000/generate
curl -s -L http://127.0.0.1:8000/auto-content
curl -s http://127.0.0.1:8000/frontend/dashboard.html
```

주의:

- `curl -I`는 FastAPI 라우트가 `HEAD`를 허용하지 않아 405가 나올 수 있다. GET으로 확인해야 한다.

---

## 10. 알려진 리스크와 다음 작업

### 리스크

- 로컬 LLM `qwen3.6:35b-a3b`는 생성 시간이 길다. 사용자에게 진행률과 중단 기능을 계속 명확히 보여줘야 한다.
- 현재 정적 HTML/CSS/JS가 페이지별로 중복되어 있다. 기능이 늘어나면 공통 레이아웃/공통 JS 분리가 필요하다.
- 발행 채널 중 유튜브/인스타그램은 실제 플랫폼 API 직접 발행보다 Webhook/드라이브 저장 중심이다.
- Notion 데이터베이스 속성명이 실제 워크스페이스와 맞지 않으면 등록이 무시될 수 있다.
- 백그라운드 작업은 현재 프로세스 메모리 기반 FastAPI BackgroundTasks다. 운영 확장 시 큐/Celery/RQ 계열로 분리하는 것이 좋다.

### 다음 작업 우선순위

1. Playwright 기반 실제 브라우저 회귀 테스트 추가
2. `/dashboard`, `/generate`, `/auto-content`, `/history` 공통 사이드바 컴포넌트화
3. 생성 세션 목록 API 추가
4. 대시보드에 최근 생성 작업 타임라인 추가
5. 자동 리서치 스케줄 실행 이력/실패 알림 강화
6. 채널별 발행 결과 로그 UI 추가
7. 실제 운영 DB 마이그레이션 도구 도입

---

## 11. 파일별 책임

| 파일 | 책임 |
|---|---|
| `main.py` | 앱 시작, 라우팅, 정적 페이지 연결, 스케줄러 실행 |
| `auth.py` | JWT 생성·검증, 사용자 소유권 검증 |
| `users.py` | 사용자 생성, 로그인, 현재 사용자 조회 |
| `personas.py` | 온보딩 답변 기반 페르소나 생성·수정 |
| `categories.py` | 카테고리 API |
| `keywords.py` | 키워드 API |
| `channels.py` | 채널 설정 API |
| `sessions.py` | 콘텐츠 생성 세션, 백그라운드 생성, 검수 처리 |
| `drafts.py` | 초안 목록·상세·삭제, 출처 표시 |
| `research.py` | 리서치 소스, 수집, 주제 제안, 자동 생성 |
| `agent.py` | LLM 프롬프트, 생성, QC |
| `publisher.py` | 승인 콘텐츠 발행 |
| `notion.py` | Notion 등록·상태 업데이트 |
| `notion_poller.py` | Notion 상태 동기화 |
| `models.py` | SQLAlchemy ORM 모델 |
| `database.py` | DB 엔진과 세션 |
| `frontend/dashboard.html` | 모니터링 대시보드 |
| `frontend/generate.html` | 수동 콘텐츠 생성 화면 |
| `frontend/auto_content.html` | 자동 콘텐츠 생성 화면 |
| `frontend/history.html` | 콘텐츠 이력·검수 화면 |
| `frontend/settings.html` | 설정 화면 |
| `frontend/onboarding.html` | 온보딩 화면 |

