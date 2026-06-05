# ContentFlow 프로젝트 인수인계 문서

> 작성일: 2026-06-05
> 작성자: 브라이언
> 버전: 0.1.0

---

## 1. 프로젝트 개요

### 서비스 정의
콘텐츠 발행 프로세스를 자동화하고 싶은 사람들을 대상으로,
AI Agent를 활용해 주제 입력 → 초안 생성 → 검수 → 자동 발행까지의
전체 파이프라인을 제공하는 SaaS 툴.

### 핵심 차별점
- 사용자별 **페르소나·스타일 파일** 자동 생성 (온보딩 기반)
- 주제 하나 입력 → 블로그·뉴스레터·유튜브·숏폼 **4채널 동시 초안 생성**
- **로컬 LLM** (Ollama) 활용 → API 과금 없음
- 사용자가 개입하는 지점: **주제 선택 + 최종 검수 승인**만

### 수익 모델 (예정)
| 단계 | 형태 | 가격 |
|---|---|---|
| 무료 유입 | 블로그·뉴스레터·유튜브·숏폼 콘텐츠 | 무료 |
| 입문 | 플레이북 PDF 판매 | 1~3만원/건 |
| 핵심 | 월 구독 멤버십 | 3~5만원/월 |
| 프리미엄 | 1:1 컨설팅 | 10~20만원/회 |

손익분기: 구독 100명 × 3만원 = 월 300만원 → 순이익 200만원 목표

---

## 2. 사업 방향

### Phase 1 — 콘텐츠 서비스로 시장 진입
- 타겟: 50~60대 재직 중인 직장인 (퇴직 고민 중)
- 핵심가치: "AI 몰라도 따라하면 수익 파이프라인이 생긴다"
- 첫 번째 플레이북: "재직 중 50대가 AI로 기획문서·보고서 대필 프리랜서로 월 100만원 버는 법"
- 운영 방식: 재직 유지 + 일 2~3시간 검수·승인만 직접

### Phase 2 — 플랫폼으로 확장
- Phase 1 유저베이스 기반으로 3번 아이템(시니어 Job 매칭)과 접목
- 정보 큐레이션 + 매칭 플랫폼으로 진화
- 매각 옵션 열어두는 구조

---

## 3. 시스템 아키텍처

### 전체 흐름
```
사용자 입력 (키워드·타겟감정)
    ↓
오케스트레이터 에이전트 (주제 후보 3개 제안)
    ↓
사용자 선택
    ↓
채널별 에이전트 (블로그·뉴스레터·유튜브·숏폼 동시 생성)
    ↓
QC 자체 검토 (8개 체크리스트)
    ↓
노션 검수 대기 큐 등록
    ↓
사용자 승인 (검수·승인만 직접)
    ↓
자동 발행 트리거 → 채널별 발행
```

### 역할 분리
| 역할 | 담당 |
|---|---|
| 콘텐츠 생성·검수 | Claude.ai (브라이언 님 직접) |
| 자동화 파이프라인 | 로컬 Python 백엔드 (Mac Studio M1) |
| LLM 엔진 | Ollama — qwen3:35b-a3b |
| 검수 관리 | 노션 데이터베이스 |
| 데이터 저장 | PostgreSQL 17/18 |

### 기술 스택
| 영역 | 기술 |
|---|---|
| 백엔드 | Python · FastAPI · SQLAlchemy (async) |
| DB | PostgreSQL 17/18 · asyncpg |
| LLM | Ollama · qwen3:35b-a3b |
| 프론트엔드 | Node.js · HTML/CSS/JS |
| 검수 관리 | Notion API |
| 발행 연동 | 티스토리·스티비·구글 드라이브 REST API |
| 하드웨어 | Mac Studio M1 32GB RAM |

---

## 4. 파일 구조

```
contentflow/
├── main.py                  # FastAPI 앱 진입점
├── database.py              # PostgreSQL 비동기 연결
├── models.py                # SQLAlchemy ORM (9개 테이블)
├── agent.py                 # 오케스트레이터 + 채널별 에이전트
├── publisher.py             # 채널별 자동 발행
├── requirements.txt
├── schema.sql               # PostgreSQL DDL 스키마
├── routers/
│   ├── users.py
│   ├── personas.py          # 온보딩 → 페르소나 생성·수정
│   ├── categories.py
│   ├── keywords.py
│   ├── channels.py          # 발행 채널 설정
│   ├── sessions.py          # 핵심 — 파이프라인 전체 흐름
│   └── drafts.py            # 검수 대기 초안 조회
├── knowledge/               # 지식 베이스 파일
│   ├── persona.md           # 브라이언 에디터 페르소나
│   ├── style.md             # 문체·구조 가이드
│   └── topic.md             # 플레이북 주제·검증 사례
├── prompts/                 # 에이전트 프롬프트
│   ├── orchestrator_prompt.md
│   ├── blog_agent_prompt.md
│   └── youtube_agent_prompt.md
└── frontend/
    ├── onboarding.html      # 온보딩 5단계 UI
    └── settings.html        # 설정 화면 UI (3개 탭)
```

---

## 5. 데이터베이스 스키마

### 테이블 목록 (9개)

| 테이블 | 역할 |
|---|---|
| `users` | 사용자 계정·온보딩 완료 여부 |
| `user_personas` | 온보딩 답변 원본 + persona.md·style.md |
| `categories` | 사용자별 카테고리 |
| `keywords` | 카테고리별 키워드·타겟 감정·경험 메모 |
| `channel_configs` | 발행 채널 연동 설정 (API 키 암호화) |
| `content_sessions` | 콘텐츠 생성 요청 단위·주제 후보·선택 결과 |
| `content_drafts` | 채널별 초안·QC 결과·검수 상태·발행 URL |
| `review_logs` | 승인·수정·반려 이력 |

### content_drafts 상태 전이
```
pending → review → approved → published
                ↘ revision → (재생성)
                ↘ rejected
```

### 핵심 설계 원칙
- `user_personas.raw_answers`: JSONB로 온보딩 원본 저장 → 언제든 파일 재생성 가능
- `content_sessions` → `content_drafts` 1:N: 주제 하나로 4채널 초안 독립 관리
- `review_logs`: 모든 검수 이력 누적 → 품질 분석 가능

---

## 6. 에이전트 구성

### 오케스트레이터 역할
1. 지식 베이스 3개 파일 로드 (persona.md · style.md · topic.md)
2. 사용자 입력 분석 → 주제 후보 3개 제안
3. 선택된 주제를 채널별 에이전트에 분배
4. 결과물 QC 검토 후 검수 대기 큐 등록

### 채널별 에이전트

| 에이전트 | 출력물 | 분량 |
|---|---|---|
| 블로그 | SEO 최적화 포스트 (마크다운) | 1,200~1,500자 |
| 뉴스레터 | 이메일 초안 (MD + HTML) | 읽기 5분 이내 |
| 유튜브 | 스크립트 + 썸네일 문구 3안 | 7~10분 분량 |
| 숏폼 | 60초 대본 (릴스·쇼츠·틱톡) | 60초 이내 |

> 뉴스레터 에이전트는 `weekly-newsletter` 스킬을 호출하는 방식으로 연동

### QC 자체 검토 체크리스트
- 금지 표현 없음 (쉽습니다·간단합니다·누구나)
- 검증 수치만 사용
- 후킹 도입이 독자 감정을 건드리는가
- 단계별 실행 방법이 구체적인가
- 오늘 당장 할 수 있는 것 1가지
- CTA 자연스럽게 연결
- 기술 용어 괄호 설명 포함
- 분량 기준 충족

---

## 7. 지식 베이스 파일

### persona.md 주요 내용
- 이름: 브라이언
- 경력: IT기술영업·보험영업·스타트업 창업·서비스기획 (25년)
- 핵심 정체성: "직접 해본 것만 전달하는 사람"
- 절대 금지: "쉽습니다·간단합니다·누구나" 류 과장, 자기자랑 톤, 기술 용어 남발
- 강점 자산: AI로 보고서 작성 시간 80% 절감 직접 검증

### style.md 주요 내용
- 말투: 해요체, 짧은 문장(40자 이내), 구체적 수치
- 구조 원칙: ① 공감 → ② 경험 → ③ 실행
- 채널별 길이 기준 명시

### topic.md 주요 내용
- 핵심 포지셔닝: "재직 중 50~60대가 AI Agent로 월 100~200만원 사이드잡 수익 만들기"
- Playbook #1 (검증 완료): AI로 수익화 파이프라인 만들기
- 절대 포함 금지: 검증되지 않은 수치, 코딩 필요 방법, 초기비용 높은 툴 (월 2만원 초과)
- SEO 키워드 목록 포함

---

## 8. API 엔드포인트

### 핵심 파이프라인
```
POST   /api/sessions/                     세션 생성 + 주제 후보 3개 반환
POST   /api/sessions/{id}/generate        주제 선택 + 백그라운드 초안 생성
GET    /api/sessions/{id}                 생성 상태 폴링
POST   /api/sessions/drafts/{id}/review   승인·수정·반려 → 자동 발행 트리거
```

### 설정 관리
```
POST   /api/users/                        사용자 생성
GET    /api/users/{id}                    사용자 조회
POST   /api/personas/generate            온보딩 답변 → 페르소나 파일 생성
PUT    /api/personas/{id}                페르소나 파일 수정
GET    /api/categories/                  카테고리 목록
POST   /api/categories/                  카테고리 추가
DELETE /api/categories/{id}              카테고리 삭제
GET    /api/keywords/                    키워드 목록
POST   /api/keywords/                    키워드 추가
DELETE /api/keywords/{id}               키워드 삭제
POST   /api/channels/                    채널 연동 설정
GET    /api/drafts/pending               검수 대기 초안 목록
GET    /api/drafts/{id}                  초안 상세 조회
```

---

## 9. 노션 검수 대기 큐

### 데이터베이스 구조
- URL: https://app.notion.com/p/773ac5a5438246d3ab5921e69d9872d1
- Data Source ID: cd24d74a-2e53-4f8b-8d54-d4abeda56955

### 컬럼 구성
| 컬럼 | 타입 | 설명 |
|---|---|---|
| 콘텐츠 제목 | Title | 초안 제목 |
| 상태 | Select | 검수 대기·승인·수정 필요·발행 완료 |
| 채널 | Select | 블로그·뉴스레터·유튜브·숏폼 |
| 생성 일시 | Created Time | 자동 |
| 주제 키워드 | Text | 입력 키워드 |
| 파일명 | Text | 로컬 파일명 |
| 수정 메모 | Text | 수정 요청 내용 |
| 발행 링크 | URL | 발행 후 링크 |

### 뷰 구성
- 기본 테이블 뷰: 전체 목록
- 📋 상태별 보드: 칸반 형태
- 🔔 검수 대기만 보기: 매일 열어보는 뷰

### 검수 워크플로우
```
에이전트 초안 생성
→ 노션 "검수 대기" 자동 등록
→ 브라이언 님이 🔔 검수 대기만 보기 열람
→ 승인: 상태를 "승인"으로 변경 → 자동 발행 트리거
→ 수정: 수정 메모 입력 후 "수정 필요"로 변경
→ 발행 완료 후: "발행 완료" + 발행 링크 입력
```

---

## 10. 온보딩 화면 (5단계)

| 단계 | 수집 정보 | DB 저장 위치 |
|---|---|---|
| Step 1 | 이름·경력·콘텐츠 목적 | `users` + `user_personas.raw_answers` |
| Step 2 | 독자층·고민·불안 | `user_personas.raw_answers` |
| Step 3 | 말투·금지표현·톤·검증 경험 | → `persona.md` + `style.md` 생성 |
| Step 4 | 채널 선택·발행 주기 | `channel_configs` |
| Step 5 | 첫 키워드·감정·제외사항 | `keywords` + `content_sessions` 초기화 |

온보딩 완료 시 LLM이 답변을 분석해서 persona.md·style.md 자동 생성 후 PostgreSQL 저장.

---

## 11. 설정 화면 (3개 탭)

### 탭 1 — 카테고리·키워드
- 카테고리 추가 (이름 + 색상 선택)
- 아코디언으로 펼치면 키워드 목록
- Enter 또는 추가 버튼으로 키워드 등록
- 키워드별 사용 횟수 표시

### 탭 2 — 발행 채널
- 블로그·뉴스레터·유튜브·숏폼 4개 카드
- 연동 상태 배지 (연동됨/미연동)
- API 키 암호화 입력 + 연결 테스트
- 발행 주기 설정

### 탭 3 — 페르소나·스타일
- 온보딩 생성 파일 직접 수정
- persona.md · style.md 인라인 편집
- 온보딩 재시작 버튼

---

## 12. 발행 채널 연동 현황

| 채널 | 연동 방식 | 상태 |
|---|---|---|
| 블로그 (티스토리) | REST API + Bearer Token | ✅ 설계 완료 |
| 뉴스레터 (스티비) | API Key + 리스트 ID | ✅ 설계 완료 |
| 유튜브 스크립트 | 구글 드라이브 API | ✅ 설계 완료 |
| 숏폼 대본 | 노션 API | ✅ 설계 완료 |

---

## 13. 로컬 실행 방법

### 사전 요구사항
```bash
# Ollama 실행 확인
ollama run qwen3:35b-a3b

# PostgreSQL DB 생성
createdb contentflow
```

### 백엔드 실행
```bash
cd contentflow
pip install -r requirements.txt

# .env 파일 생성
echo "DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/contentflow" > .env

# 스키마 적용
psql -d contentflow -f schema.sql

# 서버 실행
python main.py
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

### 프론트엔드 실행
```bash
# 브라우저에서 직접 열기
open frontend/onboarding.html
open frontend/settings.html
```

---

## 14. 다음 개발 단계 (미완성 항목)

### 즉시 시작 가능
- [ ] 숏폼 에이전트 프롬프트 작성 (`shortform_agent_prompt.md`)
- [ ] 노션 API 연동 코드 (초안 자동 등록)
- [ ] 온보딩 HTML → FastAPI 백엔드 실제 연결
- [ ] 설정 HTML → FastAPI 백엔드 실제 연결

### 중기 개발
- [ ] Node.js 프론트엔드 (대시보드·콘텐츠 생성 화면)
- [ ] API 키 암호화 모듈 (cryptography 라이브러리)
- [ ] 노션 상태 변경 감지 → 자동 발행 트리거 (폴링 or 웹훅)
- [ ] 뉴스레터 weekly-newsletter 스킬 연동

### 장기 개발
- [ ] 다중 사용자 인증 (JWT)
- [ ] 콘텐츠 성과 분석 대시보드
- [ ] Phase 2 — 시니어 Job 매칭 플랫폼 연동

---

## 15. 주요 설계 결정 사항 (의사결정 로그)

| 결정 | 이유 |
|---|---|
| 로컬 LLM 사용 | Claude Pro 구독 유지 + API 과금 없음 |
| 콘텐츠 생성은 Claude.ai 직접 | qwen3:35b 품질이 Claude API 수준 미달 |
| 노션으로 검수 관리 | 모바일 검수 가능, 이미 연결됨 |
| FastAPI 비동기 구조 | 초안 생성이 오래 걸리므로 백그라운드 태스크 필수 |
| JSONB로 raw_answers 저장 | 온보딩 질문 변경 시에도 재분석 가능 |
| 1:N 세션→초안 구조 | 채널별 초안을 독립적으로 승인·반려 가능 |

---

## 16. 산출물 목록

| 파일명 | 종류 | 설명 |
|---|---|---|
| `schema.sql` | SQL | PostgreSQL DDL (9개 테이블) |
| `main.py` | Python | FastAPI 진입점 |
| `database.py` | Python | DB 연결 |
| `models.py` | Python | ORM 모델 |
| `agent.py` | Python | 오케스트레이터·에이전트 |
| `publisher.py` | Python | 자동 발행 모듈 |
| `routers/sessions.py` | Python | 핵심 파이프라인 API |
| `routers/personas.py` | Python | 페르소나 생성 API |
| `routers/categories.py` | Python | 카테고리 CRUD |
| `routers/keywords.py` | Python | 키워드 CRUD |
| `routers/users.py` | Python | 사용자 CRUD |
| `routers/channels.py` | Python | 채널 설정 API |
| `routers/drafts.py` | Python | 초안 조회 API |
| `requirements.txt` | Text | 의존성 목록 |
| `onboarding.html` | HTML | 온보딩 5단계 UI |
| `settings.html` | HTML | 설정 화면 UI |
| `knowledge/persona.md` | Markdown | 브라이언 페르소나 |
| `knowledge/style.md` | Markdown | 문체·구조 가이드 |
| `knowledge/topic.md` | Markdown | 플레이북 주제·사례 |
| `prompts/orchestrator_prompt.md` | Markdown | 오케스트레이터 프롬프트 |
| `prompts/blog_agent_prompt.md` | Markdown | 블로그 에이전트 프롬프트 |
| `prompts/youtube_agent_prompt.md` | Markdown | 유튜브 에이전트 프롬프트 |
| `blog_post_20260604.md` | Markdown | 테스트 블로그 초안 (검수 완료) |
| `contentflow_handover.md` | Markdown | 본 인수인계 문서 |

