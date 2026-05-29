"""CLI smoke test for the OutreachGraph.

Run from the backend/ directory after installing dependencies:

    cd backend/
    uv sync --frozen
    python -m playwright install chromium
    cp .env.example .env   # fill in OPENAI_API_KEY and SERPER_API_KEY
    python scripts/test_outreach_cli.py

Expected output: research summary, email subject/body, LinkedIn note,
schedule JSON, and a confidence score — all generated end-to-end by GPT-4o.
"""

import asyncio
import sys
from pathlib import Path

# Ensure the backend/ directory is on sys.path when the script is run directly
# (e.g. python scripts/test_outreach_cli.py from inside backend/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.graphs.outreach.graph import graph
from app.graphs.outreach.state import OutreachState
from langchain_core.messages import HumanMessage


async def main() -> None:
    state: OutreachState = {
        "messages": [HumanMessage(content="Start outreach research")],
        "company_name": "Linear",
        "contact_name": "Karri Saarinen",
        "company_url": "https://linear.app",
        "product_profile": (
            '{"name": "Acme CRM", "description": "B2B sales automation tool", '
            '"target_market": "SaaS companies 50-500 employees", '
            '"key_features": ["pipeline management", "email automation", "analytics"]}'
        ),
        "research_output": "",
        "email_subject": "",
        "email_body": "",
        "linkedin_note": "",
        "data_confidence": 0.0,
        "personalization_signals": [],
        "schedule_output": "",
        "avoid_messaging": "",
    }

    print("Running OutreachGraph end-to-end (this may take 30-60 seconds)...\n")

    result: OutreachState = await graph.ainvoke(
        state,
        config={"recursion_limit": 10},
    )

    print("=" * 60)
    print("RESEARCH OUTPUT")
    print("=" * 60)
    print(result["research_output"][:500])
    if len(result["research_output"]) > 500:
        print(f"... [{len(result['research_output']) - 500} chars truncated]")

    print("\n" + "=" * 60)
    print("EMAIL SUBJECT")
    print("=" * 60)
    print(result["email_subject"])

    print("\n" + "=" * 60)
    print("EMAIL BODY")
    print("=" * 60)
    print(result["email_body"][:500])
    if len(result["email_body"]) > 500:
        print(f"... [{len(result['email_body']) - 500} chars truncated]")

    print("\n" + "=" * 60)
    print("LINKEDIN NOTE")
    print("=" * 60)
    print(result["linkedin_note"])

    print("\n" + "=" * 60)
    print("SCHEDULE OUTPUT (JSON)")
    print("=" * 60)
    print(result["schedule_output"])

    print("\n" + "=" * 60)
    print("CONFIDENCE SCORE")
    print("=" * 60)
    print(result["data_confidence"])

    print("\n" + "=" * 60)
    print("PERSONALIZATION SIGNALS")
    print("=" * 60)
    for signal in result["personalization_signals"]:
        print(f"  - {signal}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
