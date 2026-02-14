"""
Notion Client — Write research framing output to a Notion database.

Reads NOTION_API_KEY and NOTION_DATABASE_ID from environment variables.

Notion field type mapping (adjust if your database uses different types):
  - Project Name  → title
  - Owner         → rich_text
  - Research Type → select
  - Background    → rich_text
  - Purpose       → rich_text
  - RQ            → rich_text
  - Method        → rich_text
  - Result        → rich_text
  - Contribution  → rich_text
  - Year          → select
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
    """Return the target Notion database ID."""
    db_id = os.getenv("NOTION_DATABASE_ID")
    if not db_id:
        raise ValueError("NOTION_DATABASE_ID environment variable is not set.")
    return db_id


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
        "Year":         _select(framing_output.get("Year", "")),
    }

    page = notion.pages.create(
        parent={"database_id": database_id},
        properties=properties,
    )

    return page
