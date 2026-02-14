"""
ResearchFramingAgent — Notion-Mapped Pipeline

Produces a structured JSON output mapped exactly to the Notion
research project database schema.

Notion fields → Pipeline steps:
  Project Name  → Summarised from raw_input
  Owner         → Provided by caller (default: "")
  Research Type → EpistemicModeClassifier
  Background    → TensionExtractor (formatted)
  Purpose       → ResearchPositionBuilder
  RQ            → ResearchQuestionGenerator + auto-select
  Method        → MethodInferrer
  Result        → ResultInferrer
  Contribution  → ContributionClaimer
  Year          → Current year
"""

import json
import copy
from datetime import datetime
from framing_agent import run_skill

# ---------------------------------------------------------------------------
# Notion-mapped pipeline
# ---------------------------------------------------------------------------


def run_notion_pipeline(raw_input: str, owner: str = "") -> dict:
    """
    Execute the full pipeline and return output mapped to Notion schema.

    Args:
        raw_input: The user's raw research topic / idea.
        owner:     (Optional) Owner name for the Notion record.

    Returns:
        A dict with keys matching the Notion database fields.
    """

    # --- Step 1: EpistemicModeClassifier → Research Type ---
    print("[1/8] Classifying epistemic mode ...")
    mode_result = run_skill("EpistemicModeClassifier", {
        "raw_input": raw_input,
    })
    research_type = mode_result["mode"]
    print(f"       → Research Type: {research_type}")

    # --- Step 2: TensionExtractor → Background ---
    print("[2/8] Extracting epistemic tension ...")
    tension = run_skill("TensionExtractor", {
        "raw_input": raw_input,
    })
    background = (
        f"Dominant assumption: {tension['dominant_assumption']} "
        f"Blind spot: {tension['blind_spot']} "
        f"Core gap: {tension['core_gap']}"
    )
    print("       → Background extracted")

    # --- Step 3: ResearchPositionBuilder → Purpose ---
    print("[3/8] Building research position ...")
    position_result = run_skill("ResearchPositionBuilder", {
        "mode": research_type,
        "tension": tension,
    })
    purpose = position_result["research_position"]
    print(f"       → Purpose: {purpose[:80]}...")

    # --- Step 4: ResearchQuestionGenerator → RQ ---
    print("[4/8] Generating research questions ...")
    rq_result = run_skill("ResearchQuestionGenerator", {
        "research_position": purpose,
        "mode": research_type,
    })
    research_questions = rq_result["research_questions"]
    print(f"       → {len(research_questions)} questions generated")

    # --- Step 5: Auto-select first RQ ---
    print("[5/8] Auto-selecting first research question ...")
    selected_rq = research_questions[0]["question"]
    print(f"       → RQ: {selected_rq[:80]}...")

    # --- Step 6: MethodInferrer → Method ---
    print("[6/8] Inferring method ...")
    method_result = run_skill("MethodInferrer", {
        "mode": research_type,
        "selected_rq": selected_rq,
    })
    method = method_result["method"]
    print(f"       → Method: {method[:80]}...")

    # --- Step 7: ResultInferrer → Result ---
    print("[7/8] Inferring result ...")
    result_result = run_skill("ResultInferrer", {
        "mode": research_type,
        "selected_rq": selected_rq,
        "method": method,
    })
    result = result_result["result"]
    print(f"       → Result: {result[:80]}...")

    # --- Step 8: ContributionClaimer → Contribution ---
    print("[8/8] Generating contribution statement ...")
    contrib_result = run_skill("ContributionClaimer", {
        "selected_rq": selected_rq,
        "mode": research_type,
        "tension": tension,
    })
    contribution = contrib_result["contribution"]
    print(f"       → Contribution: {contribution[:80]}...")

    # --- Derive Project Name from raw_input ---
    # Capitalise and truncate to a reasonable title length
    project_name = raw_input.strip().rstrip("?!.").strip()
    if len(project_name) > 100:
        project_name = project_name[:97] + "..."

    # --- Assemble Notion output ---
    notion_output = {
        "Project Name": project_name,
        "Owner": owner,
        "Research Type": research_type,
        "Background": background,
        "Purpose": purpose,
        "RQ": selected_rq,
        "Method": method,
        "Result": result,
        "Contribution": contribution,
        "Year": str(datetime.now().year),
    }

    print("\n✅ Notion-mapped pipeline complete.")
    return notion_output


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print('Usage: python research_framing_agent.py "<your research idea>" [owner]')
        sys.exit(1)

    raw = sys.argv[1]
    owner_name = sys.argv[2] if len(sys.argv) > 2 else ""

    final = run_notion_pipeline(raw, owner=owner_name)

    print("\n" + "=" * 60)
    print("NOTION OUTPUT")
    print("=" * 60)
    print(json.dumps(final, indent=2, ensure_ascii=False))
