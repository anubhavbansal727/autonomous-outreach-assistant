"""OutreachState — shared state TypedDict for the Outreach LangGraph.

In plain English:
- Think of this as the shared "clipboard" every node in the outreach graph
  reads from and writes to. As the flow runs, fields get filled in.
- ``messages`` is special: the ``Annotated[..., operator.add]`` means new
  messages are APPENDED to the list rather than replacing it, so the running
  conversation with the LLM is never lost between steps.
- The comments below group fields by which node fills them in (input →
  research → personalize → schedule).
"""

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class OutreachState(TypedDict):
    # ------------------------------------------------------------------ #
    # Shared message accumulator
    # Each sub-graph (research ReAct loop, schedule ReAct loop) appends
    # messages here via the operator.add reducer so that no messages are
    # overwritten between graph steps.
    # ------------------------------------------------------------------ #
    messages: Annotated[list[BaseMessage], operator.add]

    # ------------------------------------------------------------------ #
    # Input fields — provided by the caller before graph.ainvoke()
    # ------------------------------------------------------------------ #
    company_name: str
    contact_name: str
    company_url: str
    product_profile: str        # JSON string of the user's product profile
    avoid_messaging: str        # Topics to avoid (always user-entered, never agent-inferred)

    # ------------------------------------------------------------------ #
    # Research node outputs
    # ------------------------------------------------------------------ #
    research_output: str        # Populated by research_node; human-readable summary

    # ------------------------------------------------------------------ #
    # Personalize node outputs
    # ------------------------------------------------------------------ #
    email_subject: str
    email_body: str
    linkedin_note: str
    data_confidence: float      # 0.0–1.0 self-assessment score from personalize_node
    personalization_signals: list[str]  # Specific details the LLM used

    # ------------------------------------------------------------------ #
    # Schedule node outputs
    # ------------------------------------------------------------------ #
    schedule_output: str        # JSON string of ScheduleOutput from extract_schedule_node
