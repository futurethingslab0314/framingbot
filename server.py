"""
FramingAgent — FastAPI Web Server

Provides REST API endpoints for the Research Framing Pipeline.
Designed for deployment on Railway.

Endpoints:
  GET  /             — Serve the frontend UI.
  GET  /health       — Health check.
  POST /run          — Run the full internal pipeline (shared state output).
  POST /notion-run   — Run the Notion-mapped pipeline + auto-write to Notion.
  POST /chat/start   — Start a guided conversation session.
  POST /chat/message — Send a message in a conversation session.
  POST /chat/logic-check — Run coherence check on current framing.
  POST /notion-sync  — Sync framing data back from Notion.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
from pathlib import Path

from framing_agent import run_pipeline
from research_framing_agent import run_notion_pipeline
from notion_writer import write_to_notion
from conversation_engine import (
    start_session,
    process_message,
    get_session,
    update_framing,
    run_logic_check,
    generate_abstract,
    rerun_from_profile,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FramingAgent API",
    description="Research Framing Pipeline — transforms a raw research idea into a structured framing artifact.",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    raw_input: str


class NotionRunRequest(BaseModel):
    raw_input: str
    owner: str = ""
    write_to_notion: bool = True


class ChatStartRequest(BaseModel):
    owner: str = ""


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class LogicCheckRequest(BaseModel):
    session_id: str


class ProfileUpdateRequest(BaseModel):
    session_id: str
    epistemic_profile: dict
    keyword_map: dict


class NotionSyncRequest(BaseModel):
    session_id: str
    notion_page_id: str


class NotionSaveRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


@app.get("/")
def serve_frontend():
    """Serve the main frontend page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Frontend not found. Place index.html in /static/"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Original pipeline endpoints
# ---------------------------------------------------------------------------


@app.post("/run")
def run_framing(request: RunRequest):
    if not request.raw_input.strip():
        raise HTTPException(status_code=400, detail="raw_input cannot be empty.")
    try:
        result = run_pipeline(request.raw_input)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notion-run")
def run_notion_framing(request: NotionRunRequest):
    if not request.raw_input.strip():
        raise HTTPException(status_code=400, detail="raw_input cannot be empty.")
    try:
        framing_output = run_notion_pipeline(request.raw_input, owner=request.owner)
        notion_page = None
        if request.write_to_notion:
            notion_page = write_to_notion(framing_output)
        return {
            "framing_output": framing_output,
            "notion": {
                "written": request.write_to_notion,
                "page_id": notion_page["id"] if notion_page else None,
                "url": notion_page.get("url") if notion_page else None,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Chat endpoints
# ---------------------------------------------------------------------------


@app.post("/chat/start")
def chat_start(request: ChatStartRequest):
    """Start a new guided conversation session."""
    try:
        result = start_session(owner=request.owner)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/message")
def chat_message(request: ChatMessageRequest):
    """Send a message in an active conversation session."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty.")
    try:
        result = process_message(request.session_id, request.message)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/logic-check")
def chat_logic_check(request: LogicCheckRequest):
    """Run coherence check on the current framing structure."""
    try:
        result = run_logic_check(request.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/generate-abstract")
def chat_generate_abstract(request: LogicCheckRequest):
    """Generate a bilingual academic abstract from the current framing."""
    try:
        result = generate_abstract(request.session_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/update-profile")
def chat_update_profile(request: ProfileUpdateRequest):
    """Re-run EpistemicRuleEngine → RQ → Method after profile/keyword changes."""
    try:
        result = rerun_from_profile(
            request.session_id,
            request.epistemic_profile,
            request.keyword_map,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/save-notion")
def chat_save_notion(request: NotionSaveRequest):
    """Save the current framing to Notion."""
    try:
        session = get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")
        framing = session["framing"]
        notion_page = write_to_notion(framing)
        return {
            "status": "saved",
            "page_id": notion_page["id"],
            "url": notion_page.get("url"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/notion-sync")
def notion_sync(request: NotionSyncRequest):
    """Sync framing data back from a Notion page into the session."""
    try:
        from notion_client import Client
        notion = Client(auth=os.getenv("NOTION_API_KEY"))
        page = notion.pages.retrieve(page_id=request.notion_page_id)

        # Extract properties
        props = page.get("properties", {})
        synced_framing = {}

        for field_name in [
            "Project Name", "Owner", "Research Type", "Background",
            "Purpose", "RQ", "Method", "Result", "Contribution", "Year"
        ]:
            prop = props.get(field_name, {})
            prop_type = prop.get("type", "")

            if prop_type == "title":
                items = prop.get("title", [])
                synced_framing[field_name] = items[0]["plain_text"] if items else ""
            elif prop_type == "rich_text":
                items = prop.get("rich_text", [])
                synced_framing[field_name] = items[0]["plain_text"] if items else ""
            elif prop_type == "select":
                sel = prop.get("select")
                synced_framing[field_name] = sel["name"] if sel else ""
            else:
                synced_framing[field_name] = ""

        # Update session framing
        updated = update_framing(request.session_id, synced_framing)

        return {
            "status": "synced",
            "framing": updated,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
