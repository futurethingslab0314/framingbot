"""
Conversation Engine — Phase-based guided dialogue manager.

Manages conversation sessions, tracks phases, calls skills for
structure extraction, and maintains the framing state.
"""

import json
import os
import re
import uuid
import copy
from datetime import datetime
from openai import OpenAI
from chat_prompts import PHASE_PROMPTS, OPENING_MESSAGE
from framing_agent import run_skill

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
client = OpenAI()

# ---------------------------------------------------------------------------
# Phase order
# ---------------------------------------------------------------------------

PHASE_ORDER = [
    "greeting",
    "tension_discovery",
    "positioning",
    "question_sharpening",
    "method_contribution",
    "complete",
]

# ---------------------------------------------------------------------------
# Session store (in-memory; swap for Redis/DB in production)
# ---------------------------------------------------------------------------

sessions: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_framing() -> dict:
    """Return an empty framing structure."""
    return {
        "Project Name": "",
        "Owner": "",
        "Research Type": "",
        "Background": "",
        "Purpose": "",
        "RQ": "",
        "Method": "",
        "Result": "",
        "Contribution": "",
        "Year": str(datetime.now().year),
    }


def _extract_tag(text: str) -> dict | None:
    """Extract JSON from <extract>...</extract> tags in LLM response."""
    match = re.search(r"<extract>(.*?)</extract>", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _clean_response(text: str) -> str:
    """Remove <extract> tags from the user-facing response."""
    return re.sub(r"\s*<extract>.*?</extract>\s*", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------


def start_session(owner: str = "") -> dict:
    """
    Start a new conversation session.

    Returns:
        {session_id, agent_message, phase, framing}
    """
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "phase": "greeting",
        "phase_index": 0,
        "messages": [],           # full chat history for OpenAI
        "framing": _empty_framing(),
        "owner": owner,
        "raw_input_parts": [],    # accumulate user descriptions
        "rq_candidates": [],      # store generated RQ candidates
    }
    session["framing"]["Owner"] = owner
    sessions[session_id] = session

    return {
        "session_id": session_id,
        "agent_message": OPENING_MESSAGE,
        "phase": "greeting",
        "framing": session["framing"],
    }


def process_message(session_id: str, user_message: str) -> dict:
    """
    Process a user message and return the agent reply + updated framing.

    Returns:
        {agent_message, phase, framing, extraction_happened}
    """
    session = sessions.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    # Accumulate raw input
    session["raw_input_parts"].append(user_message)

    # If still in greeting, advance to tension_discovery
    if session["phase"] == "greeting":
        session["phase"] = "tension_discovery"
        session["phase_index"] = 1

    # Get current phase prompt
    phase_config = PHASE_PROMPTS[session["phase"]]
    system_prompt = phase_config["system"]

    # Build messages for OpenAI
    session["messages"].append({"role": "user", "content": user_message})

    openai_messages = [
        {"role": "system", "content": system_prompt},
    ] + session["messages"]

    # Call OpenAI
    response = client.chat.completions.create(
        model=MODEL,
        messages=openai_messages,
        temperature=0.7,
        max_tokens=800,
    )

    raw_reply = response.choices[0].message.content or ""

    # Check for extraction signal
    extract_signal = _extract_tag(raw_reply)
    agent_message = _clean_response(raw_reply)
    extraction_happened = False

    if extract_signal and extract_signal.get("ready"):
        extraction_happened = True
        _run_extraction(session, extract_signal)

        # Advance to next phase
        next_index = session["phase_index"] + 1
        if next_index < len(PHASE_ORDER):
            session["phase"] = PHASE_ORDER[next_index]
            session["phase_index"] = next_index

    # Store assistant reply
    session["messages"].append({"role": "assistant", "content": agent_message})

    return {
        "agent_message": agent_message,
        "phase": session["phase"],
        "framing": session["framing"],
        "extraction_happened": extraction_happened,
    }


def get_session(session_id: str) -> dict | None:
    """Get a session by ID."""
    return sessions.get(session_id)


def update_framing(session_id: str, framing: dict) -> dict:
    """Update the framing structure for a session (e.g., after Notion sync)."""
    session = sessions.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")
    session["framing"].update(framing)
    return session["framing"]


# ---------------------------------------------------------------------------
# Extraction logic — calls existing skills
# ---------------------------------------------------------------------------


def _run_extraction(session: dict, signal: dict):
    """Run the appropriate skill extraction based on the phase signal."""
    phase = signal.get("phase")
    raw_input = " ".join(session["raw_input_parts"])
    framing = session["framing"]

    if phase == "tension":
        # Run EpistemicModeClassifier
        mode_result = run_skill("EpistemicModeClassifier", {
            "raw_input": raw_input,
        })
        framing["Research Type"] = mode_result.get("mode", "")

        # Run TensionExtractor
        tension = run_skill("TensionExtractor", {
            "raw_input": raw_input,
        })
        framing["Background"] = (
            f"Dominant assumption: {tension.get('dominant_assumption', '')} "
            f"Blind spot: {tension.get('blind_spot', '')} "
            f"Core gap: {tension.get('core_gap', '')}"
        )
        session["_tension"] = tension

    elif phase == "positioning":
        tension = session.get("_tension", {})
        mode = framing.get("Research Type", "")
        position_result = run_skill("ResearchPositionBuilder", {
            "mode": mode,
            "tension": tension,
        })
        framing["Purpose"] = position_result.get("research_position", "")

    elif phase == "question":
        mode = framing.get("Research Type", "")
        purpose = framing.get("Purpose", "")

        # Generate 3 RQs
        rq_result = run_skill("ResearchQuestionGenerator", {
            "research_position": purpose,
            "mode": mode,
        })
        rq_list = rq_result.get("research_questions", [])
        session["rq_candidates"] = rq_list

        # Auto-select based on signal or default to first
        selected_idx = signal.get("selected_index", 0)
        if 0 <= selected_idx < len(rq_list):
            framing["RQ"] = rq_list[selected_idx].get("question", "")
        elif rq_list:
            framing["RQ"] = rq_list[0].get("question", "")

    elif phase == "method_contribution":
        mode = framing.get("Research Type", "")
        selected_rq = framing.get("RQ", "")
        tension = session.get("_tension", {})

        # MethodInferrer
        method_result = run_skill("MethodInferrer", {
            "mode": mode,
            "selected_rq": selected_rq,
        })
        framing["Method"] = method_result.get("method", "")

        # ResultInferrer
        result_result = run_skill("ResultInferrer", {
            "mode": mode,
            "selected_rq": selected_rq,
            "method": framing["Method"],
        })
        framing["Result"] = result_result.get("result", "")

        # ContributionClaimer
        contrib_result = run_skill("ContributionClaimer", {
            "selected_rq": selected_rq,
            "mode": mode,
            "tension": tension,
        })
        framing["Contribution"] = contrib_result.get("contribution", "")

        # Set project name
        raw_input = " ".join(session["raw_input_parts"])
        framing["Project Name"] = raw_input[:100].strip().rstrip("?!.").strip()


def run_logic_check(session_id: str) -> dict:
    """
    Run CoherenceChecker on the current framing.

    Returns the coherence check result.
    """
    session = sessions.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found.")

    framing = session["framing"]
    tension = session.get("_tension", {})

    result = run_skill("CoherenceChecker", {
        "mode": framing.get("Research Type", ""),
        "selected_rq": framing.get("RQ", ""),
        "tension": tension,
        "contribution": framing.get("Contribution", ""),
    })

    return result
