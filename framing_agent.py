"""
FramingAgent — Research Framing Pipeline Orchestrator

Executes 10 sequential steps to transform a raw research input into
a fully structured framing artifact with coherence validation.

Pipeline:
  1.  NotionKeywordSync          → keyword_map, keyword_roles, epistemic_profile
  2.  EpistemicModeClassifier    → mode (may refine epistemic_profile / keyword_map)
  3.  EpistemicRuleEngine        → rule_engine_output (dominant_orientation, rq_templates,
                                    method_bias, contribution_bias, logic_pattern)
  4.  TensionExtractor           → tension
  5.  ResearchPositionBuilder    → research_position
  6.  ResearchQuestionGenerator  → research_questions[]
  7.  MethodLogicAligner         → method + alignment_rationale
  8.  ContributionClaimer        → result_type + contribution
  9.  CoherenceChecker           → coherence_notes
  10. AbstractGenerator          → abstract_en + abstract_zh
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
    "epistemic_profile": {
        "exploratory": 0.0,
        "critical": 0.0,
        "problem_solving": 0.0,
        "constructive": 0.0,
    },
    "keyword_map": {
        "exploratory": [],
        "critical": [],
        "problem_solving": [],
        "constructive": [],
    },
    "keyword_roles": {},
    "rule_engine_output": {
        "dominant_orientation": "",
        "rq_templates": [],
        "method_bias": [],
        "contribution_bias": [],
        "logic_pattern": "",
    },
    "research_position": "",
    "research_questions": [],
    "selected_rq": "",
    "method": "",
    "result_type": "",
    "contribution": "",
    "coherence_notes": {
        "logical_gaps": [],
        "scope_issues": [],
        "alignment_assessment": "",
    },
    "abstract_en": "",
    "abstract_zh": "",
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
# Partial re-run helper (used by /api/apply-keywords)
# ---------------------------------------------------------------------------


def update_keywords(state: dict, keywords: list) -> dict:
    """
    Re-run NotionKeywordSync + EpistemicRuleEngine with new keywords
    and update *state* in-place.

    Args:
        state:    The current shared-state dict (mutated in-place).
        keywords: Flat list of keyword objects [{term, role, weight?}, …].

    Returns:
        The updated state dict.
    """
    # 1. NotionKeywordSync
    print("[update_keywords] Running NotionKeywordSync ...")
    result = run_skill("NotionKeywordSync", {"keywords": keywords})
    state["keyword_map"] = result.get("keyword_map", state["keyword_map"])
    state["keyword_roles"] = result.get("keyword_roles", {})
    state["epistemic_profile"] = result.get(
        "epistemic_profile", state["epistemic_profile"]
    )

    # 2. EpistemicRuleEngine
    print("[update_keywords] Re-running EpistemicRuleEngine ...")
    result = run_skill("EpistemicRuleEngine", {
        "epistemic_profile": state["epistemic_profile"],
        "keyword_map": state["keyword_map"],
        "keyword_roles": state["keyword_roles"],
    })
    state["rule_engine_output"] = {
        "dominant_orientation": result.get("dominant_orientation", ""),
        "rq_templates": result.get("rq_templates", []),
        "method_bias": result.get("method_bias", []),
        "contribution_bias": result.get("contribution_bias", []),
        "logic_pattern": result.get("logic_pattern", ""),
    }
    print(
        f"[update_keywords] → dominant: "
        f"{state['rule_engine_output']['dominant_orientation']}"
    )

    return state


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(raw_input: str, keywords: list | None = None) -> dict:
    """
    Execute the full FramingAgent pipeline (10 steps).

    Args:
        raw_input:  The user's raw research topic / idea.
        keywords:   Optional list of keyword objects [{term, role, weight?}, …]
                    from Notion or other sources.

    Returns:
        The final shared state dict (the structured framing artifact).
    """
    state = copy.deepcopy(INITIAL_STATE)
    state["raw_input"] = raw_input

    # --- Step 1: NotionKeywordSync ---
    print("[1/10] Running NotionKeywordSync ...")
    kw_input = keywords if keywords else []
    result = run_skill("NotionKeywordSync", {
        "keywords": kw_input,
    })
    state["keyword_map"] = result.get("keyword_map", state["keyword_map"])
    state["keyword_roles"] = result.get("keyword_roles", {})
    state["epistemic_profile"] = result.get("epistemic_profile", state["epistemic_profile"])
    print(f"       → keyword_map populated, profile calculated")

    # --- Step 2: EpistemicModeClassifier ---
    print("[2/10] Running EpistemicModeClassifier ...")
    result = run_skill("EpistemicModeClassifier", {
        "raw_input": state["raw_input"],
    })
    state["mode"] = result["mode"]
    # Merge classifier-provided profile/keywords if available (additive)
    if "epistemic_profile" in result:
        for k, v in result["epistemic_profile"].items():
            if k in state["epistemic_profile"]:
                state["epistemic_profile"][k] = max(state["epistemic_profile"][k], v)
    if "keyword_map" in result:
        for k, v in result["keyword_map"].items():
            if k in state["keyword_map"]:
                existing = set(state["keyword_map"][k])
                existing.update(v)
                state["keyword_map"][k] = list(existing)
    print(f"       → mode: {state['mode']}")

    # --- Step 3: EpistemicRuleEngine ---
    print("[3/10] Running EpistemicRuleEngine ...")
    result = run_skill("EpistemicRuleEngine", {
        "epistemic_profile": state["epistemic_profile"],
        "keyword_map": state["keyword_map"],
        "keyword_roles": state["keyword_roles"],
    })
    state["rule_engine_output"] = {
        "dominant_orientation": result.get("dominant_orientation", ""),
        "rq_templates": result.get("rq_templates", []),
        "method_bias": result.get("method_bias", []),
        "contribution_bias": result.get("contribution_bias", []),
        "logic_pattern": result.get("logic_pattern", ""),
    }
    print(f"       → dominant: {state['rule_engine_output']['dominant_orientation']}")

    reo = state["rule_engine_output"]

    # --- Step 4: TensionExtractor ---
    print("[4/10] Running TensionExtractor ...")
    result = run_skill("TensionExtractor", {
        "raw_input": state["raw_input"],
        "keyword_map": state["keyword_map"],
    })
    state["tension"] = {
        "dominant_assumption": result["dominant_assumption"],
        "blind_spot": result["blind_spot"],
        "core_gap": result["core_gap"],
    }
    print("       → tension extracted")

    # --- Step 5: ResearchPositionBuilder ---
    print("[5/10] Running ResearchPositionBuilder ...")
    result = run_skill("ResearchPositionBuilder", {
        "mode": state["mode"],
        "tension": state["tension"],
        "keyword_map": state["keyword_map"],
        "dominant_orientation": reo["dominant_orientation"],
    })
    state["research_position"] = result["research_position"]
    print(f"       → position: {state['research_position'][:80]}...")

    # --- Step 6: ResearchQuestionGenerator ---
    print("[6/10] Running ResearchQuestionGenerator ...")
    result = run_skill("ResearchQuestionGenerator", {
        "research_position": state["research_position"],
        "rq_templates": reo["rq_templates"],
        "logic_pattern": reo["logic_pattern"],
        "dominant_orientation": reo["dominant_orientation"],
        "keyword_map": state["keyword_map"],
    })
    state["research_questions"] = result["research_questions"]
    print(f"       → {len(state['research_questions'])} questions generated")

    # Auto-select first RQ
    if state["research_questions"]:
        state["selected_rq"] = state["research_questions"][0]["question"]
        print(f"       → selected: {state['selected_rq'][:80]}...")

    # --- Step 7: MethodLogicAligner ---
    print("[7/10] Running MethodLogicAligner ...")
    result = run_skill("MethodLogicAligner", {
        "selected_rq": state["selected_rq"],
        "method_bias": reo["method_bias"],
        "contribution_bias": reo["contribution_bias"],
        "dominant_orientation": reo["dominant_orientation"],
        "logic_pattern": reo["logic_pattern"],
        "keyword_map": state["keyword_map"],
        "tension": state["tension"],
    })
    state["method"] = result.get("method", "")
    print(f"       → method: {state['method'][:80]}...")

    # --- Step 8: ContributionClaimer ---
    print("[8/10] Running ContributionClaimer ...")
    result = run_skill("ContributionClaimer", {
        "selected_rq": state["selected_rq"],
        "mode": state["mode"],
        "tension": state["tension"],
        "keyword_map": state["keyword_map"],
        "contribution_bias": reo["contribution_bias"],
    })
    state["result_type"] = result["result_type"]
    state["contribution"] = result["contribution"]
    print(f"       → result_type: {state['result_type']}")

    # --- Step 9: CoherenceChecker ---
    print("[9/10] Running CoherenceChecker ...")
    result = run_skill("CoherenceChecker", {
        "mode": state["mode"],
        "selected_rq": state["selected_rq"],
        "tension": state["tension"],
        "contribution": state["contribution"],
        "method": state["method"],
        "keyword_map": state["keyword_map"],
    })
    state["coherence_notes"] = {
        "logical_gaps": result["logical_gaps"],
        "scope_issues": result["scope_issues"],
        "alignment_assessment": result["alignment_assessment"],
    }
    print(f"       → alignment: {state['coherence_notes']['alignment_assessment'][:80]}...")

    # --- Step 10: AbstractGenerator ---
    print("[10/10] Running AbstractGenerator ...")
    result = run_skill("AbstractGenerator", {
        "background": f"{state['tension']['dominant_assumption']} "
                      f"{state['tension']['blind_spot']} "
                      f"{state['tension']['core_gap']}",
        "purpose": state["research_position"],
        "method": state["method"],
        "result": state.get("result_type", ""),
        "contribution": state["contribution"],
        "epistemic_profile": state["epistemic_profile"],
        "rule_engine_output": state["rule_engine_output"],
        "keyword_map": state["keyword_map"],
    })
    state["abstract_en"] = result.get("abstract_en", "")
    state["abstract_zh"] = result.get("abstract_zh", "")
    print("       → abstracts generated")

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

