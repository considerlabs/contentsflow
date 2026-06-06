import json
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

import agent
from auth import get_current_user
from models import User

router = APIRouter()
_SETTINGS_FILE = Path("settings.json")


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    existing = _load()
    existing.update(data)
    _SETTINGS_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


def apply_saved_settings() -> None:
    data = _load()
    if data.get("provider"):
        agent.LLM_PROVIDER = data["provider"]
    if data.get("ollama_model"):
        agent.OLLAMA_MODEL = data["ollama_model"]
    if data.get("ollama_url"):
        agent.OLLAMA_URL = data["ollama_url"]
    if data.get("claude_model"):
        agent.CLAUDE_MODEL = data["claude_model"]
    if data.get("claude_api_key"):
        agent.CLAUDE_API_KEY = data["claude_api_key"]
    if data.get("gemini_model"):
        agent.GEMINI_MODEL = data["gemini_model"]
    if data.get("gemini_api_key"):
        agent.GEMINI_API_KEY = data["gemini_api_key"]


class LLMUpdate(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    ollama_url: Optional[str] = None


@router.get("")
async def get_settings(user: User = Depends(get_current_user)):
    available: List[str] = []
    if agent.LLM_PROVIDER == "ollama":
        base_url = agent.OLLAMA_URL.rsplit("/api/", 1)[0]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{base_url}/api/tags")
                if res.status_code == 200:
                    available = [m["name"] for m in res.json().get("models", [])]
        except Exception:
            pass
    return {
        "provider": agent.LLM_PROVIDER,
        "ollama_model": agent.OLLAMA_MODEL,
        "ollama_url": agent.OLLAMA_URL,
        "claude_model": agent.CLAUDE_MODEL,
        "has_claude_key": bool(agent.CLAUDE_API_KEY),
        "gemini_model": agent.GEMINI_MODEL,
        "has_gemini_key": bool(agent.GEMINI_API_KEY),
        "available_models": available,
    }


@router.put("")
async def update_settings(body: LLMUpdate, user: User = Depends(get_current_user)):
    provider = body.provider.strip()
    if provider:
        agent.LLM_PROVIDER = provider

    save_data: dict = {"provider": agent.LLM_PROVIDER}

    if provider == "ollama":
        if body.model and body.model.strip():
            agent.OLLAMA_MODEL = body.model.strip()
        if body.ollama_url and body.ollama_url.strip():
            agent.OLLAMA_URL = body.ollama_url.strip()
        save_data["ollama_model"] = agent.OLLAMA_MODEL
        save_data["ollama_url"] = agent.OLLAMA_URL

    elif provider == "claude":
        if body.model and body.model.strip():
            agent.CLAUDE_MODEL = body.model.strip()
        if body.api_key and body.api_key.strip():
            agent.CLAUDE_API_KEY = body.api_key.strip()
        save_data["claude_model"] = agent.CLAUDE_MODEL
        if body.api_key and body.api_key.strip():
            save_data["claude_api_key"] = agent.CLAUDE_API_KEY

    elif provider == "gemini":
        if body.model and body.model.strip():
            agent.GEMINI_MODEL = body.model.strip()
        if body.api_key and body.api_key.strip():
            agent.GEMINI_API_KEY = body.api_key.strip()
        save_data["gemini_model"] = agent.GEMINI_MODEL
        if body.api_key and body.api_key.strip():
            save_data["gemini_api_key"] = agent.GEMINI_API_KEY

    _save(save_data)

    available: List[str] = []
    if agent.LLM_PROVIDER == "ollama":
        base_url = agent.OLLAMA_URL.rsplit("/api/", 1)[0]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{base_url}/api/tags")
                if res.status_code == 200:
                    available = [m["name"] for m in res.json().get("models", [])]
        except Exception:
            pass

    return {
        "provider": agent.LLM_PROVIDER,
        "ollama_model": agent.OLLAMA_MODEL,
        "ollama_url": agent.OLLAMA_URL,
        "claude_model": agent.CLAUDE_MODEL,
        "has_claude_key": bool(agent.CLAUDE_API_KEY),
        "gemini_model": agent.GEMINI_MODEL,
        "has_gemini_key": bool(agent.GEMINI_API_KEY),
        "available_models": available,
    }
