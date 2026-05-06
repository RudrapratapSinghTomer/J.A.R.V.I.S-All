from __future__ import annotations
import os
from typing import Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psutil

# We will set this global reference from main_async.py
_mind_ref: Optional[Any] = None

app = FastAPI(title="J.A.R.V.I.S. 2.0 API")


@app.get("/health")
async def health():
    return {"status": "ok", "message": "J.A.R.V.I.S. API is online"}


# Enable CORS for local dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import RedirectResponse


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/dashboard/")


# Mount the web dashboard
web_dir = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
)
print(f"DEBUG: Dashboard directory: {web_dir}")
if not os.path.exists(web_dir):
    print(f"ERROR: Dashboard directory NOT FOUND at {web_dir}")

app.mount("/dashboard", StaticFiles(directory=web_dir, html=True), name="dashboard")


class SystemStatus(BaseModel):
    cpu: float
    memory: float
    mood: str
    urgency: float
    authenticated: bool
    owner: str
    uptime_events: int


@app.get("/api/status")
async def get_status():
    if not _mind_ref:
        raise HTTPException(status_code=503, detail="Mind not initialized")

    heart = _mind_ref.heart
    return {
        "cpu": psutil.cpu_percent(),
        "memory": psutil.virtual_memory().percent,
        "mood": heart.emotion.name,
        "urgency": heart.emotion.intensity,
        "authenticated": heart.identity.authenticated,
        "owner": heart.owner_name,
        "uptime_events": len(_mind_ref.history),
        "health": heart.health.__dict__,
        "thinking": _mind_ref.thinking,
        "thought": _mind_ref.current_thought,
    }


@app.get("/api/history")
async def get_history():
    if not _mind_ref:
        return []

    return [
        {
            "content": event.content,
            "created_at": event.created_at,
            "metadata": event.metadata,
        }
        for event in _mind_ref.history[-20:]
    ]


@app.get("/api/agents")
async def get_agents():
    if not _mind_ref:
        return {}

    return {aid: agent.describe() for aid, agent in _mind_ref.agents.items()}


class CommandRequest(BaseModel):
    command: str


@app.post("/api/command")
async def post_command(req: CommandRequest):
    if not _mind_ref:
        raise HTTPException(status_code=503, detail="Mind not initialized")

    decision = await _mind_ref.handle_event(
        req.command, metadata={"source": "dashboard", "auth_confidence": 0.8}
    )
    return {
        "response": decision.response,
        "intent": decision.intent,
        "agents": decision.agents,
    }


def set_mind(mind: Any):
    global _mind_ref
    _mind_ref = mind
