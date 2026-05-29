import json

from langchain_core.tools import tool


# Hardcoded mock CRM pipeline data.
# In production this would query the outreach_jobs / CRM table directly.
_MOCK_PIPELINE: list[dict] = [
    {
        "company": "Acme Corp",
        "stage": "Negotiating",
        "last_contact": "2026-05-10",
        "deal_value": 48000,
    },
    {
        "company": "GlobalTech Inc",
        "stage": "Demo",
        "last_contact": "2026-05-20",
        "deal_value": 24000,
    },
    {
        "company": "Nexus Payments",
        "stage": "Closed",
        "last_contact": "2026-04-15",
        "deal_value": 72000,
    },
    {
        "company": "Vortex Labs",
        "stage": "Prospect",
        "last_contact": "2026-05-01",
        "deal_value": 18000,
    },
    {
        "company": "Prism Analytics",
        "stage": "Contacted",
        "last_contact": "2026-05-25",
        "deal_value": 36000,
    },
]


@tool
def get_crm_pipeline() -> str:
    """Retrieve the current CRM pipeline to check for existing relationships.

    Use this tool before recommending send timing to identify whether the
    prospect is already in the pipeline. If a match is found, set
    flag_for_human to true in your output.

    Returns:
        A JSON string containing a list of CRM pipeline records, each with
        fields: company, stage, last_contact (ISO date), deal_value (integer USD).
    """
    return json.dumps(_MOCK_PIPELINE, indent=2)
