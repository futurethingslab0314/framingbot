"""
FramingAgent — Research Framing Pipeline Orchestrator

Executes 7 sequential steps to transform a raw research input into
a fully structured framing artifact with coherence validation.

Pipeline:
  1. EpistemicModeClassifier   → mode
  2. TensionExtractor          → tension
  3. ResearchPositionBuilder   → research_position
  4. ResearchQuestionGenerator → research_questions[]
  5. Auto-select first RQ      → selected_rq
  6. ContributionClaimer       → result_type + contribution
  7. CoherenceChecker          → coherence_notes
"""

import json
import os
import copy
from pathlib import Path
from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SKILLS_DIR = Path(__file__).parent / "skills"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

INITIAL_STATE = {
    "raw_input": "",
    "mode": "",
    "tension": {
        "dominant_assumption": "",
        "blind_spot": "",
        "core_gap": "",
    },
    "research_position": "",
    "research_questions": [],
    "selected_rq": "",
    "result_type": "",
    "contribution": "",
    "coherence_notes": {
        "logical_gaps": [],
        "scope_issues": [],
        "alignment_assessment": "",
    },
}

# ---------------------------------------------------------------------------
# OpenAI client (reads OPENAI_API_KEY from environment automatically)
# ---------------------------------------------------------------------------

client = OpenAI()

# ---------------------------------------------------------------------------
# Skill loader helpers
# ---------------------------------------------------------------------------


def load_skill_prompt(skill_name: str) -> str:
    """Load the prompt.md content for a given skill."""
    prompt_path = SKILLS_DIR / skill_name / "prompt.md"
    return prompt_path.read_text(encoding="utf-8")


def load_skill_config(skill_name: str) -> dict:
    """Load the skill.json configuration for a given skill."""
    config_path = SKILLS_DIR / skill_name / "skill.json"
    return json.loads(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# LLM call via OpenAI
# ---------------------------------------------------------------------------


def call_llm(system_prompt: str, user_message: str, **kwargs) -> dict:
    """
    Call OpenAI Chat Completions and return parsed JSON.

    Args:
        system_prompt: The skill prompt (from prompt.md).
        user_message:  JSON-serialised input for the skill.
        **kwargs:      Model parameters (temperature, max_tokens).

    Returns:
        Parsed JSON dict from the LLM response.
    """
    temperature = kwargs.get("temperature", 0)
    max_tokens = kwargs.get("max_tokens", 500)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return json.loads(content)


# ---------------------------------------------------------------------------
# Individual skill runner
# ---------------------------------------------------------------------------


def run_skill(skill_name: str, skill_input: dict) -> dict:
    """
    Run a single skill: load its prompt, call the LLM, return parsed output.
    """
    prompt = load_skill_prompt(skill_name)
    config = load_skill_config(skill_name)
    model_params = config.get("model_requirements", {})

    user_message = json.dumps(skill_input, ensure_ascii=False)
    result = call_llm(
        system_prompt=prompt,
        user_message=user_message,
        **model_params,
    )
    return result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(raw_input: str) -> dict:
    """
    Execute the full FramingAgent pipeline.

    Args:
        raw_input: The user's raw research topic / idea.

    Returns:
        The final shared state dict (the structured framing artifact).
    """
    state = copy.deepcopy(INITIAL_STATE)
    state["raw_input"] = raw_input

    # --- Step 1: EpistemicModeClassifier ---
    print("[1/7] Running EpistemicModeClassifier ...")
    result = run_skill("EpistemicModeClassifier", {
        "raw_input": state["raw_input"],
    })
    state["mode"] = result["mode"]
    print(f"       → mode: {state['mode']}")

    # --- Step 2: TensionExtractor ---
    print("[2/7] Running TensionExtractor ...")
    result = run_skill("TensionExtractor", {
        "raw_input": state["raw_input"],
    })
    state["tension"] = {
        "dominant_assumption": result["dominant_assumption"],
        "blind_spot": result["blind_spot"],
        "core_gap": result["core_gap"],
    }
    print("       → tension extracted")

    # --- Step 3: ResearchPositionBuilder ---
    print("[3/7] Running ResearchPositionBuilder ...")
    result = run_skill("ResearchPositionBuilder", {
        "mode": state["mode"],
        "tension": state["tension"],
    })
    state["research_position"] = result["research_position"]
    print(f"       → position: {state['research_position'][:80]}...")

    # --- Step 4: ResearchQuestionGenerator ---
    print("[4/7] Running ResearchQuestionGenerator ...")
    result = run_skill("ResearchQuestionGenerator", {
        "research_position": state["research_position"],
        "mode": state["mode"],
    })
    state["research_questions"] = result["research_questions"]
    print(f"       → {len(state['research_questions'])} questions generated")

    # --- Step 5: Auto-select first RQ ---
    print("[5/7] Auto-selecting first research question ...")
    state["selected_rq"] = state["research_questions"][0]["question"]
    print(f"       → selected: {state['selected_rq'][:80]}...")

    # --- Step 6: ContributionClaimer ---
    print("[6/7] Running ContributionClaimer ...")
    result = run_skill("ContributionClaimer", {
        "selected_rq": state["selected_rq"],
        "mode": state["mode"],
        "tension": state["tension"],
    })
    state["result_type"] = result["result_type"]
    state["contribution"] = result["contribution"]
    print(f"       → result_type: {state['result_type']}")

    # --- Step 7: CoherenceChecker ---
    print("[7/7] Running CoherenceChecker ...")
    result = run_skill("CoherenceChecker", {
        "mode": state["mode"],
        "selected_rq": state["selected_rq"],
        "tension": state["tension"],
        "contribution": state["contribution"],
    })
    state["coherence_notes"] = {
        "logical_gaps": result["logical_gaps"],
        "scope_issues": result["scope_issues"],
        "alignment_assessment": result["alignment_assessment"],
    }
    print(f"       → alignment: {state['coherence_notes']['alignment_assessment'][:80]}...")

    print("\n✅ Pipeline complete.")
    return state


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python framing_agent.py \"<your research idea>\"")
        sys.exit(1)

    raw = " ".join(sys.argv[1:])
    final_state = run_pipeline(raw)

    print("\n" + "=" * 60)
    print("FINAL FRAMING ARTIFACT")
    print("=" * 60)
    print(json.dumps(final_state, indent=2, ensure_ascii=False))
