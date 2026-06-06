# ============================================
# ContentFlow — FastAPI 백엔드 메인
# ============================================
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

from database import engine, Base
import users, personas, categories, keywords, channels, sessions, drafts, research

@asynccontextmanager
async def lifespan(app: FastAPI):
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE user_personas ADD COLUMN IF NOT EXISTS topic_md TEXT NOT NULL DEFAULT ''"
        ))
        await conn.execute(text(
            "ALTER TABLE content_sessions ADD COLUMN IF NOT EXISTS error_message TEXT"
        ))
        await conn.execute(text(
            "ALTER TABLE content_sessions ADD COLUMN IF NOT EXISTS generation_current_channel VARCHAR(50)"
        ))
        await conn.execute(text(
            "ALTER TABLE content_sessions ADD COLUMN IF NOT EXISTS generation_done INTEGER NOT NULL DEFAULT 0"
        ))
        await conn.execute(text(
            "ALTER TABLE content_sessions ADD COLUMN IF NOT EXISTS generation_total INTEGER NOT NULL DEFAULT 0"
        ))
    import asyncio
    from notion_poller import run_poller
    asyncio.create_task(run_poller())
    asyncio.create_task(research.research_scheduler())
    yield

app = FastAPI(
    title="ContentFlow API",
    description="콘텐츠 자동화 파이프라인 SaaS",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# 라우터 등록
app.include_router(users.router,      prefix="/api/users",      tags=["users"])
app.include_router(personas.router,   prefix="/api/personas",   tags=["personas"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(keywords.router,   prefix="/api/keywords",   tags=["keywords"])
app.include_router(channels.router,   prefix="/api/channels",   tags=["channels"])
app.include_router(sessions.router,   prefix="/api/sessions",   tags=["sessions"])
app.include_router(drafts.router,     prefix="/api/drafts",     tags=["drafts"])
app.include_router(research.router,    prefix="/api/research",   tags=["research"])

@app.get("/health")
async def health(): return {"status": "ok"}

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard")
async def dashboard():
    return RedirectResponse(url="/frontend/dashboard.html")

@app.get("/history")
async def history(request: Request):
    target = "/frontend/history.html"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target)

@app.get("/settings")
async def settings_page():
    return RedirectResponse(url="/frontend/settings.html")

@app.get("/onboarding")
async def onboarding():
    return RedirectResponse(url="/frontend/onboarding.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
