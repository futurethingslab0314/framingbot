"""
Notion Client — Read/write research framing data with Notion.

Environment variables:
  NOTION_API_KEY          — Notion integration token (shared by both databases)
  NOTION_DATABASE_ID      — Framing results database (write target)
  NOTION_KEYWORD_DB_ID    — Keywords database (read source for fetch_keywords)

Framing DB field mapping:
  - Project Name  → title
  - Owner         → rich_text
  - Research Type → select
  - Background    → rich_text
  - Purpose       → rich_text
  - RQ            → rich_text
  - Method        → rich_text
  - Result        → rich_text
  - Contribution  → rich_text
  - Year          → rich_text

Keyword DB field mapping (adjust names to match your database):
  - Name          → title   → term
  - Role          → select  → role  (exploratory / critical / problem_solving / constructive)
  - Weight        → number  → weight (0–1, optional, defaults to 1.0)
"""

import os
from notion_client import Client


def get_notion_client() -> Client:
    """Create and return a Notion API client."""
    token = os.getenv("NOTION_API_KEY")
    if not token:
        raise ValueError("NOTION_API_KEY environment variable is not set.")
    return Client(auth=token)


def get_database_id() -> str:
    """Return the Framing-results Notion database ID."""
    db_id = os.getenv("NOTION_DATABASE_ID")
    if not db_id:
        raise ValueError("NOTION_DATABASE_ID environment variable is not set.")
    return db_id


def get_keyword_database_id() -> str:
    """Return the Keyword Notion database ID."""
    db_id = os.getenv("NOTION_KEYWORD_DB_ID")
    if not db_id:
        raise ValueError("NOTION_KEYWORD_DB_ID environment variable is not set.")
    return db_id


# ---------------------------------------------------------------------------
# Keyword DB property names  (adjust to match your Notion database)
# ---------------------------------------------------------------------------

_KW_PROP_TERM   = "Name"    # title column   → keyword term
_KW_PROP_ROLE   = "Role"    # select column   → epistemic orientation
_KW_PROP_WEIGHT = "Weight"  # number column   → importance weight (optional)

# Valid epistemic orientations
_VALID_ROLES = {"exploratory", "critical", "problem_solving", "constructive"}



def _rich_text(value: str) -> dict:
    """Helper: build a rich_text property value."""
    return {
        "rich_text": [
            {
                "type": "text",
                "text": {"content": value[:2000]},  # Notion 2000 char limit
            }
        ]
    }


def _title(value: str) -> dict:
    """Helper: build a title property value."""
    return {
        "title": [
            {
                "type": "text",
                "text": {"content": value[:2000]},
            }
        ]
    }


def _select(value: str) -> dict:
    """Helper: build a select property value."""
    return {
        "select": {"name": value}
    }


def _multi_select(value: str) -> dict:
    """Helper: build a multi_select property value from a comma-separated string."""
    names = [v.strip() for v in value.split(",") if v.strip()] if value else []
    return {
        "multi_select": [{"name": n} for n in names]
    }


def write_to_notion(framing_output: dict) -> dict:
    """
    Write a framing output dict to the Notion database.

    Args:
        framing_output: Dict with Notion-mapped keys
            (Project Name, Owner, Research Type, Background,
             Purpose, RQ, Method, Result, Contribution, Year).

    Returns:
        The created Notion page object (dict).
    """
    notion = get_notion_client()
    database_id = get_database_id()

    properties = {
        "Project Name": _title(framing_output.get("Project Name", "")),
        "Owner":        _rich_text(framing_output.get("Owner", "")),
        "Research Type": _select(framing_output.get("Research Type", "")),
        "Background":   _rich_text(framing_output.get("Background", "")),
        "Purpose":      _rich_text(framing_output.get("Purpose", "")),
        "RQ":           _rich_text(framing_output.get("RQ", "")),
        "Method":       _rich_text(framing_output.get("Method", "")),
        "Result":       _rich_text(framing_output.get("Result", "")),
        "Contribution": _rich_text(framing_output.get("Contribution", "")),
        "Year":         _rich_text(framing_output.get("Year", "")),
    }

    page = notion.pages.create(
        parent={"database_id": database_id},
        properties=properties,
    )

    return page


# ---------------------------------------------------------------------------
# Keyword database reader
# ---------------------------------------------------------------------------


def fetch_keywords() -> dict:
    """
    Query the Keyword Notion database and return keywords grouped by
    epistemic orientation.

    Returns:
        {
            "keywords": [ {term, role, weight}, … ],   # flat list
            "keyword_map": {                             # grouped
                "exploratory": [...],
                "critical": [...],
                "problem_solving": [...],
                "constructive": [...]
            }
        }
    """
    notion = get_notion_client()
    db_id = get_keyword_database_id()

    # Paginate through all rows
    all_rows: list[dict] = []
    start_cursor = None
    while True:
        query_args: dict = {"database_id": db_id, "page_size": 100}
        if start_cursor:
            query_args["start_cursor"] = start_cursor
        response = notion.databases.query(**query_args)
        all_rows.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        start_cursor = response.get("next_cursor")

    # Parse each row into {term, role, weight}
    keywords: list[dict] = []
    keyword_map: dict[str, list[str]] = {
        "exploratory": [],
        "critical": [],
        "problem_solving": [],
        "constructive": [],
    }

    for page in all_rows:
        props = page.get("properties", {})

        # --- term (title column) ---
        term_prop = props.get(_KW_PROP_TERM, {})
        title_items = term_prop.get("title", [])
        term = title_items[0]["plain_text"].strip() if title_items else ""
        if not term:
            continue

        # --- role (select column) ---
        role_prop = props.get(_KW_PROP_ROLE, {})
        role_sel = role_prop.get("select")
        role = role_sel["name"].strip().lower().replace(" ", "_") if role_sel else ""
        if role not in _VALID_ROLES:
            continue  # skip rows with unknown or missing role

        # --- weight (number column, optional) ---
        weight_prop = props.get(_KW_PROP_WEIGHT, {})
        weight = weight_prop.get("number")
        if weight is None:
            weight = 1.0

        keywords.append({"term": term, "role": role, "weight": weight})
        keyword_map[role].append(term)

    return {
        "keywords": keywords,
        "keyword_map": keyword_map,
    }
