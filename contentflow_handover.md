# ContentFlow 프로젝트 인수인계 문서

> 작성일: 2026-06-05
> 최종 업데이트: 2026-06-05
> 작성자: 브라이언
> 현재 버전: 0.2.0

---

## 1. 현재 결론

ContentFlow는 로컬 환경에서 콘텐츠 생성, 검수, 블로그 자동 발행, 그리고 뉴스레터·유튜브·인스타그램용 재활용 초안을 만드는 MVP입니다.

현재 방향은 **블로그 글을 원문 허브로 발행하고, 같은 원본 기획 패키지를 뉴스레터·유튜브·인스타그램으로 변환하는 one source multi use 전략**입니다.

핵심 LLM은 **Ollama `qwen3.6:35b-a3b`**입니다. 이 모델명은 맞는 값이며 기본값으로 유지했습니다.

---

## 2. 이번 작업에서 정리한 내용

### 완료한 수정

- `agent.py`
  - `qwen3.6:35b-a3b`를 기본 모델로 유지
  - `OLLAMA_MODEL`, `OLLAMA_URL` 환경변수 지원 추가
  - 주제 후보 생성 후 바로 채널별 작성하던 구조를 변경
  - **원본 기획 패키지** 생성 후 블로그·뉴스레터·유튜브·인스타그램 초안으로 변환
  - LLM JSON 응답 파싱 안정화
  - 뉴스레터 HTML 추출 보강
  - QC 체크 항목 확대
  - Ollama 연결 실패, HTTP 오류, 타임아웃, 빈 응답을 사람이 읽을 수 있는 메시지로 변환

- `sessions.py`
  - 잘못된 UUID가 500으로 터지지 않도록 400 처리
  - `/api/sessions/`에서 Ollama 오류 발생 시 500 대신 502와 원인 메시지 반환
  - 초안 생성 실패 시 `content_sessions.status = failed`, `error_message` 저장
  - 승인 처리 시 블로그만 자동 발행
  - 뉴스레터·유튜브·인스타그램은 승인된 재활용 콘텐츠 자산으로 보관
  - 지원 채널 검증 추가: `blog`, `newsletter`, `youtube`, `shortform`

- `models.py`
  - `ContentSession.error_message` 컬럼 추가

- `main.py`
  - 서버 시작 시 `content_sessions.error_message` 컬럼 보강
  - 기존 `user_personas.topic_md` 보강 유지

- `publisher.py`
  - 블로그 채널 설정이 없으면 `publish_failed`
  - 비블로그 채널 설정이 없어도 실패 처리하지 않고 승인 자산으로 보관
  - 알 수 없는 채널은 명시적 오류 처리

- `notion.py`, `notion_poller.py`
  - `shortform` 표시명을 인스타그램으로 변경
  - 노션 승인 시 블로그는 자동 발행, 비블로그는 승인 상태로 보관

- `channels.py`
  - 채널 설정 업데이트 시 API 키를 비워 저장해도 기존 키가 삭제되지 않도록 수정
  - 기존 채널 저장 시 `is_active = True` 보강

- 프론트엔드
  - `frontend/onboarding.html`
    - 블로그·뉴스레터·유튜브·인스타그램 4채널 기본 선택
    - 숏폼 표기를 인스타그램으로 변경
  - `frontend/dashboard.html`
    - 주제 선택 후 4채널 기본 생성
    - 생성 실패 시 `failed`와 `error_message` 표시
    - 블로그는 `승인·발행`, 비블로그는 `승인`으로 버튼 문구 분리
    - 백엔드 `detail` 에러 메시지 파싱 개선
  - `frontend/history.html`
    - 숏폼 필터를 인스타그램으로 변경
    - `approved + published`를 `승인·발행 완료`로 집계
  - `frontend/settings.html`
    - 인스타그램 채널 설명을 릴스 대본·캡션 저장으로 변경

### 삭제하거나 정리한 오래된 전제

- `schema.sql` 파일 기준 실행 설명 삭제
- `routers/` 폴더 구조 설명 삭제
- `knowledge/`, `prompts/` 폴더 산출물 설명 삭제
- Node.js 프론트엔드라는 설명 삭제
- `qwen3:35b-a3b` 모델명 삭제
- "콘텐츠 생성은 Claude.ai 직접"이라는 운영 전제 삭제
- 5단계 온보딩 설명 삭제. 실제 화면은 6단계임
- 4채널 모두 자동 발행된다는 설명 삭제. 현재 자동 발행은 블로그 중심임

---

## 3. 서비스 정의

### 목표 사용자

- 50~60대 재직 중인 직장인
- 퇴직 후 수입 단절을 걱정하는 사람
- AI를 직접 깊게 배우기보다, 검증된 실행 흐름을 따라 콘텐츠와 부수입 파이프라인을 만들고 싶은 사람

### 핵심 가치

- "AI 몰라도 따라하면 수익 파이프라인이 생긴다"
- 사용자는 키워드 입력, 주제 선택, 최종 검수에 집중
- 시스템은 주제 후보, 원본 기획 패키지, 채널별 초안, 검수 큐 등록을 자동화

### one source multi use 전략

1. 블로그 글을 원문 허브로 생성
2. 같은 원본 기획 패키지를 뉴스레터 초안으로 변환
3. 같은 원본 기획 패키지를 유튜브 스크립트로 변환
4. 같은 원본 기획 패키지를 인스타그램 릴스 대본·캡션으로 변환
5. 블로그는 승인 시 자동 발행
6. 나머지 채널은 승인된 재활용 콘텐츠 자산으로 보관

---

## 4. 현재 시스템 흐름

```text
사용자 입력
  - 키워드
  - 타겟 감정
  - 제외할 내용
    ↓
오케스트레이터
  - 주제 후보 3개 생성
    ↓
사용자 주제 선택
    ↓
원본 기획 패키지 생성
  - core_angle
  - reader_problem
  - promise
  - proof_points
  - outline
  - forbidden_claims
  - cta
  - channel_strategy
    ↓
채널별 초안 생성
  - 블로그
  - 뉴스레터
  - 유튜브
  - 인스타그램
    ↓
QC 검사
    ↓
DB 저장 + 노션 검수 대기 큐 등록
    ↓
사용자 검수
    ↓
블로그 승인 시 자동 발행
뉴스레터·유튜브·인스타그램 승인 시 자산 보관
```

---

## 5. 기술 스택

| 영역 | 기술 |
|---|---|
| 백엔드 | Python, FastAPI, SQLAlchemy async |
| DB | PostgreSQL, asyncpg |
| LLM | Ollama `qwen3.6:35b-a3b` |
| 프론트엔드 | 정적 HTML/CSS/JS |
| 검수 큐 | Notion API |
| 발행 | 블로그 REST API 중심 |
| 보안 | `cryptography.Fernet` 기반 API 키 암호화 |

---

## 6. 실제 파일 구조

```text
contentsflow/
├── main.py                  # FastAPI 앱 진입점
├── database.py              # PostgreSQL 비동기 연결
├── models.py                # SQLAlchemy ORM 모델
├── agent.py                 # 주제 후보, 원본 기획 패키지, 채널별 초안 생성
├── sessions.py              # 핵심 콘텐츠 생성·검수 API
├── drafts.py                # 검수 대기·이력 초안 조회
├── publisher.py             # 블로그 자동 발행 및 채널 발행 함수
├── notion.py                # 노션 검수 큐 등록·상태 업데이트
├── notion_poller.py         # 노션 승인·수정 상태 폴링
├── crypto.py                # API 키 암호화·복호화
├── users.py                 # 사용자 CRUD
├── personas.py              # 온보딩 기반 페르소나 생성·수정
├── categories.py            # 카테고리 CRUD
├── keywords.py              # 키워드 CRUD
├── channels.py              # 채널 설정 저장
├── requirements.txt
├── contentflow_handover.md
└── frontend/
    ├── onboarding.html      # 온보딩
    ├── dashboard.html       # 콘텐츠 생성·검수
    ├── settings.html        # 카테고리·채널·페르소나 설정
    └── history.html         # 콘텐츠 이력
```

현재 존재하지 않는 파일 또는 폴더:

- `schema.sql`
- `routers/`
- `knowledge/`
- `prompts/`
- `blog_post_20260604.md`

---

## 7. 데이터베이스 모델

현재 ORM 기준 테이블은 8개입니다.

| 테이블 | 역할 |
|---|---|
| `users` | 사용자 계정, 온보딩 완료 여부 |
| `user_personas` | 온보딩 원본 답변, persona/style/topic 문서 |
| `categories` | 사용자별 카테고리 |
| `keywords` | 카테고리별 키워드, 감정, 메모, 제외 주제 |
| `channel_configs` | 발행 채널 설정, API 키 암호화 저장 |
| `content_sessions` | 콘텐츠 생성 요청 단위, 주제 후보, 선택 주제, 상태, 오류 메시지 |
| `content_drafts` | 채널별 초안, QC 결과, 상태, 노션 페이지, 발행 URL |
| `review_logs` | 승인·수정·반려 이력 |

### 주요 상태

`content_sessions.status`

```text
pending → topic_select → generating → review
                            ↘ failed
```

`content_drafts.status`

```text
pending → review → approved
                ↘ revision
                ↘ rejected
                ↘ published
                ↘ publish_failed
```

### 자동 컬럼 보강

서버 시작 시 `main.py`에서 다음 컬럼을 보강합니다.

- `user_personas.topic_md`
- `content_sessions.error_message`

---

## 8. 핵심 API

### 콘텐츠 생성

```text
POST /api/sessions/
```

역할:

- 사용자 페르소나 조회
- 등록 키워드 조회
- Ollama로 주제 후보 3개 생성
- 세션 저장

오류 처리:

- 잘못된 UUID: 400
- 페르소나 없음: 404
- Ollama 연결/모델/타임아웃 문제: 502

```text
POST /api/sessions/{session_id}/generate
```

역할:

- 선택 주제 저장
- 채널 검증
- 백그라운드 초안 생성 시작
- 원본 기획 패키지 생성
- 채널별 초안 생성
- QC 검사
- DB 저장
- 노션 큐 등록

```text
GET /api/sessions/{session_id}
```

역할:

- 생성 상태 폴링
- `failed` 상태일 때 `error_message` 반환

```text
POST /api/sessions/drafts/{draft_id}/review
```

역할:

- `approved`, `revision`, `rejected` 처리
- 블로그 승인 시 자동 발행
- 비블로그 승인 시 승인 자산으로 보관

### 기타 API

```text
POST   /api/users/
GET    /api/users/{id}
POST   /api/personas/generate
GET    /api/personas/?user_id={id}
PUT    /api/personas/{id}
GET    /api/categories/?user_id={id}
POST   /api/categories/
DELETE /api/categories/{id}
GET    /api/keywords/?user_id={id}
POST   /api/keywords/
DELETE /api/keywords/{id}
GET    /api/channels/?user_id={id}
POST   /api/channels/
GET    /api/drafts/pending?user_id={id}
GET    /api/drafts/published?user_id={id}
GET    /api/drafts/{id}
DELETE /api/drafts/{id}
```

---

## 9. 프론트엔드 화면

### `frontend/onboarding.html`

현재 6단계입니다.

| 단계 | 내용 |
|---|---|
| 1 | 이름, 이메일, 경력, 콘텐츠 목적 |
| 2 | 독자층, 고민, 불안 |
| 3 | 말투, 금지 표현, 검증 경험 |
| 4 | 콘텐츠 전략, 포지셔닝, 플레이북, SEO, 금지 내용 |
| 5 | 발행 채널 선택 |
| 6 | 첫 카테고리와 키워드 |

특이사항:

- 4채널이 기본 선택됨
- 선택 채널은 `channel_configs`에 저장

### `frontend/dashboard.html`

역할:

- 키워드 기반 주제 후보 생성
- 주제 선택
- 4채널 기본 생성
- 생성 상태 폴링
- 실패 시 `error_message` 표시
- 검수 대기 초안 조회
- 초안 상세 모달
- 승인, 수정 요청, 반려 처리

버튼 동작:

- 블로그: `승인·발행`
- 뉴스레터·유튜브·인스타그램: `승인`

### `frontend/settings.html`

역할:

- 카테고리·키워드 관리
- 채널 설정 저장
- persona/style/topic 편집

채널 설정 주의:

- API 키 입력란을 비워 저장해도 기존 키는 삭제되지 않음
- 연결 테스트 버튼은 아직 실제 테스트 미구현

### `frontend/history.html`

역할:

- 전체 생성 이력 조회
- 채널 필터
- 검색
- 본문 모달
- 발행 링크 표시

집계:

- `승인·발행 완료`는 `approved + published` 합산

---

## 10. 노션 검수 큐

### 설정

```text
NOTION_API_KEY
NOTION_DB_ID=cd24d74a-2e53-4f8b-8d54-d4abeda56955
```

### 상태 매핑

| 내부 상태 | 노션 표시 |
|---|---|
| `approved` | 승인 |
| `revision` | 수정 필요 |
| `rejected` | 수정 필요 |
| `published` | 발행 완료 |

### 노션 승인 처리

- 노션 상태가 `승인`이고 DB 초안이 `review`일 때 처리
- 블로그는 자동 발행
- 뉴스레터·유튜브·인스타그램은 `approved`로 저장

---

## 11. 발행 전략

### 현재 운영 기준

| 채널 | 현재 처리 |
|---|---|
| 블로그 | 승인 시 자동 발행 시도 |
| 뉴스레터 | 초안 생성 후 승인 자산으로 보관 |
| 유튜브 | 스크립트 생성 후 승인 자산으로 보관 |
| 인스타그램 | 릴스 대본·캡션 생성 후 승인 자산으로 보관 |

### 구현상 남아 있는 발행 함수

`publisher.py`에는 다음 함수가 있습니다.

- `_publish_blog`
- `_publish_newsletter`
- `_save_to_drive`

다만 현재 검수 API에서는 블로그만 자동 발행합니다. 비블로그 자동 발행은 실제 API 계약 검증 후 켜는 것이 안전합니다.

---

## 12. 로컬 실행 방법

### 1. PostgreSQL 준비

```bash
createdb contentflow
```

`.env` 예시:

```bash
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/contentflow
ENCRYPTION_KEY=
NOTION_API_KEY=
NOTION_DB_ID=cd24d74a-2e53-4f8b-8d54-d4abeda56955
OLLAMA_MODEL=qwen3.6:35b-a3b
OLLAMA_URL=http://localhost:11434/api/generate
```

`ENCRYPTION_KEY`는 선택값입니다. 없으면 API 키가 평문 저장됩니다.

### 2. Ollama 실행

```bash
ollama serve
ollama run qwen3.6:35b-a3b
```

모델 확인:

```bash
curl http://localhost:11434/api/tags
```

현재 확인된 모델:

```text
qwen3.6:35b-a3b
```

### 3. FastAPI 실행

```bash
python3 main.py
```

기본 주소:

```text
http://localhost:8000
http://localhost:8000/docs
http://localhost:8000/frontend/dashboard.html
```

### 4. 현재 실행 확인 결과

2026-06-05 확인 기준:

- FastAPI: `http://localhost:8000/health` 정상
- Ollama: `http://localhost:11434/api/tags` 정상
- `qwen3.6:35b-a3b` 모델 존재 확인

---

## 13. 최근 테스트 결과

실행한 검증:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/cf_pycache python3 -m py_compile *.py
```

결과:

- Python 문법 검사 통과

```bash
node ... frontend script syntax check
```

결과:

- `frontend/onboarding.html`
- `frontend/dashboard.html`
- `frontend/settings.html`
- `frontend/history.html`

위 4개 HTML의 script 문법 검사 통과

FastAPI 오류 처리 테스트:

```text
POST /api/sessions/
body: {"user_id": "bad-id", "input_keyword": "test"}
```

결과:

```text
400 {'detail': 'user_id 값이 올바른 UUID가 아닙니다.'}
```

Ollama 꺼진 상태의 함수 테스트:

```text
Ollama에 연결할 수 없습니다. Ollama 서버를 실행하고 qwen3.6:35b-a3b 모델을 준비해 주세요.
```

---

## 14. 알려진 리스크

### 1. 인증 없음

현재는 `localStorage.cf_user_id` 기반입니다. 외부 공개용 SaaS로 쓰면 안 됩니다.

필요한 작업:

- JWT 또는 세션 기반 인증
- 사용자별 데이터 접근 권한 검증

### 2. 실제 외부 발행 API 미검증

블로그, 뉴스레터, 구글 드라이브 API 함수는 있지만 실제 API 계약 검증이 필요합니다.

필요한 작업:

- 티스토리 실제 발행 테스트
- 스티비 실제 API 테스트
- 구글 드라이브 multipart 업로드 테스트
- 실패 시 사용자에게 표시되는 메시지 개선

### 3. QC는 아직 규칙 기반

현재 QC는 문자열과 형식 중심입니다. 고품질 콘텐츠 검수로는 부족합니다.

필요한 작업:

- LLM 기반 2차 QC
- 금지어, 검증 수치, 독자 감정, 실행 가능성 평가 분리
- QC 실패 시 자동 수정 제안

### 4. 마이그레이션 체계 없음

현재는 `create_all`과 `ALTER TABLE IF NOT EXISTS`로 보강합니다.

필요한 작업:

- Alembic 도입
- 스키마 변경 이력 관리

### 5. 프론트엔드는 정적 HTML

현재는 빠른 MVP에는 적합하지만 유지보수성이 낮습니다.

필요한 작업:

- 공통 API 클라이언트 분리
- 공통 사이드바/토스트/모달 컴포넌트화
- 빌드 도구 도입 여부 검토

---

## 15. 다음 작업 우선순위

### 1순위

- 실제 콘텐츠 생성 엔드투엔드 테스트
  - 온보딩 완료 사용자
  - 키워드 입력
  - 주제 후보 생성
  - 4채널 초안 생성
  - 노션 등록
  - 블로그 승인 발행

### 2순위

- 블로그 발행 API 실제 계약 검증
- 발행 실패 메시지 UI 개선
- `publish_failed` 상태의 재시도 버튼 추가

### 3순위

- LLM 기반 QC 고도화
- 생성 결과 품질 평가 로그 저장
- 성과 분석용 필드 추가

### 4순위

- 인증
- 배포
- 결제 또는 멤버십 연동

---

## 16. 산출물 목록

| 파일명 | 설명 |
|---|---|
| `main.py` | FastAPI 진입점, 테이블 생성 및 컬럼 보강 |
| `database.py` | DB 연결 |
| `models.py` | ORM 모델 |
| `agent.py` | LLM 호출, 주제 후보, 원본 기획 패키지, 채널별 초안 생성 |
| `sessions.py` | 핵심 콘텐츠 생성·검수 API |
| `drafts.py` | 검수 대기·발행 이력 조회 |
| `publisher.py` | 발행 함수 |
| `notion.py` | 노션 페이지 생성·상태 업데이트 |
| `notion_poller.py` | 노션 상태 폴링 |
| `crypto.py` | API 키 암호화·복호화 |
| `users.py` | 사용자 API |
| `personas.py` | 페르소나 API |
| `categories.py` | 카테고리 API |
| `keywords.py` | 키워드 API |
| `channels.py` | 채널 설정 API |
| `frontend/onboarding.html` | 온보딩 화면 |
| `frontend/dashboard.html` | 콘텐츠 생성·검수 화면 |
| `frontend/settings.html` | 설정 화면 |
| `frontend/history.html` | 콘텐츠 이력 화면 |
| `requirements.txt` | Python 의존성 |
| `contentflow_handover.md` | 본 문서 |

---

## 17. 운영 메모

- 현재 FastAPI 서버는 8000 포트에서 실행 확인됨
- 현재 Ollama 서버는 11434 포트에서 실행 확인됨
- 8000 포트가 이미 점유되어 있으면 기존 Python/uvicorn 서버가 떠 있을 가능성이 높음
- `python3 main.py`는 `reload=True`라 파일 감시 권한 이슈가 날 수 있음
- 개발 중 샌드박스 환경에서는 `uvicorn main:app --host 0.0.0.0 --port 8000`처럼 reload 없이 실행하는 편이 안정적

