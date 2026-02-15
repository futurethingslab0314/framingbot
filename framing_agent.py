"""
FramingAgent — Research Framing Pipeline Orchestrator

Executes 9 sequential steps to transform a raw research input into
a fully structured framing artifact with coherence validation.

Pipeline:
  1. EpistemicModeClassifier   → mode
  2. TensionExtractor          → tension
  3. EpistemicRuleEngine        → rule_engine_output (dominant_orientation, rq_templates, method_bias, logic_pattern)
  4. ResearchPositionBuilder   → research_position
  5. ResearchQuestionGenerator → research_questions[]
  6. MethodInferrer            → method (using method_bias)
  7. ContributionClaimer       → result_type + contribution
  8. CoherenceChecker          → coherence_notes
  9. AbstractGenerator         → abstract_en + abstract_zh
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
    "rule_engine_output": {
        "dominant_orientation": "",
        "rq_templates": [],
        "method_bias": [],
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
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(raw_input: str) -> dict:
    """
    Execute the full FramingAgent pipeline (9 steps).

    Args:
        raw_input: The user's raw research topic / idea.

    Returns:
        The final shared state dict (the structured framing artifact).
    """
    state = copy.deepcopy(INITIAL_STATE)
    state["raw_input"] = raw_input

    # --- Step 1: EpistemicModeClassifier ---
    print("[1/9] Running EpistemicModeClassifier ...")
    result = run_skill("EpistemicModeClassifier", {
        "raw_input": state["raw_input"],
    })
    state["mode"] = result["mode"]
    # Also populate epistemic_profile from classifier scores if available
    if "epistemic_profile" in result:
        state["epistemic_profile"] = result["epistemic_profile"]
    if "keyword_map" in result:
        state["keyword_map"] = result["keyword_map"]
    print(f"       → mode: {state['mode']}")

    # --- Step 2: TensionExtractor ---
    print("[2/9] Running TensionExtractor ...")
    result = run_skill("TensionExtractor", {
        "raw_input": state["raw_input"],
    })
    state["tension"] = {
        "dominant_assumption": result["dominant_assumption"],
        "blind_spot": result["blind_spot"],
        "core_gap": result["core_gap"],
    }
    print("       → tension extracted")

    # --- Step 3: EpistemicRuleEngine ---
    print("[3/9] Running EpistemicRuleEngine ...")
    result = run_skill("EpistemicRuleEngine", {
        "epistemic_profile": state["epistemic_profile"],
        "keyword_map": state["keyword_map"],
    })
    state["rule_engine_output"] = {
        "dominant_orientation": result["dominant_orientation"],
        "rq_templates": result["rq_templates"],
        "method_bias": result["method_bias"],
        "logic_pattern": result["logic_pattern"],
    }
    print(f"       → dominant: {state['rule_engine_output']['dominant_orientation']}")

    # --- Step 4: ResearchPositionBuilder ---
    print("[4/9] Running ResearchPositionBuilder ...")
    result = run_skill("ResearchPositionBuilder", {
        "mode": state["mode"],
        "tension": state["tension"],
    })
    state["research_position"] = result["research_position"]
    print(f"       → position: {state['research_position'][:80]}...")

    # --- Step 5: ResearchQuestionGenerator ---
    print("[5/9] Running ResearchQuestionGenerator ...")
    reo = state["rule_engine_output"]
    result = run_skill("ResearchQuestionGenerator", {
        "research_position": state["research_position"],
        "rq_templates": reo["rq_templates"],
        "logic_pattern": reo["logic_pattern"],
        "dominant_orientation": reo["dominant_orientation"],
    })
    state["research_questions"] = result["research_questions"]
    print(f"       → {len(state['research_questions'])} questions generated")

    # Auto-select first RQ
    state["selected_rq"] = state["research_questions"][0]["question"]
    print(f"       → selected: {state['selected_rq'][:80]}...")

    # --- Step 6: MethodInferrer ---
    print("[6/9] Running MethodInferrer ...")
    result = run_skill("MethodInferrer", {
        "selected_rq": state["selected_rq"],
        "method_bias": reo["method_bias"],
        "dominant_orientation": reo["dominant_orientation"],
        "logic_pattern": reo["logic_pattern"],
    })
    state["method"] = result["method"]
    print(f"       → method: {state['method'][:80]}...")

    # --- Step 7: ContributionClaimer ---
    print("[7/9] Running ContributionClaimer ...")
    result = run_skill("ContributionClaimer", {
        "selected_rq": state["selected_rq"],
        "mode": state["mode"],
        "tension": state["tension"],
    })
    state["result_type"] = result["result_type"]
    state["contribution"] = result["contribution"]
    print(f"       → result_type: {state['result_type']}")

    # --- Step 8: CoherenceChecker ---
    print("[8/9] Running CoherenceChecker ...")
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

    # --- Step 9: AbstractGenerator ---
    print("[9/9] Running AbstractGenerator ...")
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
