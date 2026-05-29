"""OutreachGraph — LangGraph StateGraph for B2B outreach generation.

Graph topology
--------------

    START
      │
      ▼
  research_node  ◄──────────────────────────────────────────────────────┐
      │                                                                  │
      │ has tool_calls?                                                  │
      ├── YES ──► research_tools_node ────────────────────────────────── ┘
      │
      └── NO ──► personalize_node
                      │
                      ▼
                 schedule_node  ◄──────────────────────────────────────── ┐
                      │                                                    │
                      │ has tool_calls?                                    │
                      ├── YES ──► schedule_tools_node ──────────────────── ┘
                      │
                      └── NO ──► extract_schedule_node
                                        │
                                        ▼
                                       END

Rules (enforced by CLAUDE.md)
------------------------------
- Tool functions are NEVER called directly inside node functions.
  Nodes return AIMessage objects; ToolNode executes tool calls.
- Structured output uses llm.with_structured_output() — never output_json.
- recursion_limit=10 is set on ainvoke/astream calls, not here.
- No YAML, no CrewAI patterns, no max_iter.
"""

import json
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.tools.crm import get_crm_pipeline
from app.tools.scrape import scrape_website
from app.tools.search import web_search

from .state import OutreachState


# ---------------------------------------------------------------------------
# Structured output schemas
# ---------------------------------------------------------------------------


class OutreachDraftOutput(BaseModel):
    """Structured output from the personalize node."""

    email_subject: str = Field(
        description="Email subject line. Max 100 characters. No emojis."
    )
    email_body: str = Field(
        description=(
            "Plain text email body. Approximately 150-200 words. No HTML tags. "
            "Feel researched and specific, not templated."
        )
    )
    linkedin_note: str = Field(
        description="LinkedIn connection note. Plain text. Max 300 characters."
    )
    data_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Self-assessed confidence score between 0.0 and 1.0 reflecting how "
            "well-personalised the draft is based on available research data. "
            "Use 0.8+ only when specific company signals were incorporated."
        ),
    )
    personalization_signals: list[str] = Field(
        description=(
            "List of specific details from research that were woven into the draft, "
            "e.g. 'Series B funding in March 2026', 'uses Salesforce', 'expanding to EMEA'."
        )
    )


class ScheduleOutput(BaseModel):
    """Structured output from the schedule extraction node."""

    send_at: str = Field(
        description=(
            "ISO 8601 datetime string with timezone offset for the recommended send time, "
            "e.g. '2026-06-03T09:30:00-05:00'."
        )
    )
    channel: str = Field(
        description="Outreach channel. Always 'email' in v1."
    )
    recommended_window: str = Field(
        description="Human-readable send window, e.g. 'Tuesday 10-11am CT'."
    )
    flag_for_human: bool = Field(
        description=(
            "Set to true if the prospect appears in the CRM pipeline or if "
            "confidence is below 0.5. Triggers a human review alert in the UI."
        )
    )
    reason: str = Field(
        description=(
            "Brief explanation of the send time recommendation and any flags, "
            "e.g. 'Prospect in CRM at Negotiating stage — review before sending.'"
        )
    )


# ---------------------------------------------------------------------------
# LLM instances — lazily initialised to allow import without OPENAI_API_KEY
# ---------------------------------------------------------------------------

_research_llm_with_tools = None
_personalize_llm = None
_schedule_llm_with_tools = None
_schedule_extract_llm = None


def _get_research_llm():
    global _research_llm_with_tools
    if _research_llm_with_tools is None:
        _research_llm_with_tools = ChatOpenAI(model="gpt-4o", temperature=0.1).bind_tools(
            [web_search, scrape_website]
        )
    return _research_llm_with_tools


def _get_personalize_llm():
    global _personalize_llm
    if _personalize_llm is None:
        _personalize_llm = ChatOpenAI(model="gpt-4o", temperature=0.7).with_structured_output(
            OutreachDraftOutput
        )
    return _personalize_llm


def _get_schedule_llm():
    global _schedule_llm_with_tools
    if _schedule_llm_with_tools is None:
        _schedule_llm_with_tools = ChatOpenAI(model="gpt-4o", temperature=0.1).bind_tools(
            [get_crm_pipeline]
        )
    return _schedule_llm_with_tools


def _get_schedule_extract_llm():
    global _schedule_extract_llm
    if _schedule_extract_llm is None:
        _schedule_extract_llm = ChatOpenAI(model="gpt-4o", temperature=0.0).with_structured_output(
            ScheduleOutput
        )
    return _schedule_extract_llm


# ---------------------------------------------------------------------------
# Tool nodes
# ---------------------------------------------------------------------------

research_tools_node = ToolNode([web_search, scrape_website])
schedule_tools_node = ToolNode([get_crm_pipeline])


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def research_node(state: OutreachState) -> dict:
    """ReAct research agent.

    Invokes the LLM bound with web_search and scrape_website tools.
    On each call the LLM either:
      (a) requests a tool call → we return the AIMessage; ToolNode executes it.
      (b) produces a final answer → we extract the text as research_output.

    The conditional edge decides which case applies by inspecting tool_calls
    on the last message.
    """
    system_prompt = SystemMessage(
        content=(
            "You are a B2B research analyst. Your job is to gather accurate, "
            "specific information about a prospect company to support personalised "
            "outreach by a sales team.\n\n"
            "Research the following:\n"
            "1. Company overview: industry, size (employee count), HQ location, "
            "   business model, key customers.\n"
            "2. Recent signals: funding rounds, product launches, partnerships, "
            "   expansions, or leadership changes in 2025-2026.\n"
            "3. Tech stack: technologies inferred from job postings, integrations "
            "   pages, or engineering blog posts.\n"
            "4. Pain points: challenges the company likely faces based on their "
            "   stage, industry, and growth trajectory.\n\n"
            "Use the web_search tool for broad discovery. Use scrape_website on the "
            "company homepage or a specific page when you need deeper detail.\n\n"
            "IMPORTANT: Call web_search at most TWICE per research session. "
            "Do not loop endlessly — when you have enough data, produce your "
            "final research summary as plain text."
        )
    )

    # Build the message list: system prompt + all accumulated messages so far.
    # On the first call state['messages'] contains only the initial HumanMessage.
    # On subsequent calls (after tool results) it contains tool result messages too.
    messages = [system_prompt] + state["messages"]

    # If we have no user-level task message yet, inject one now.
    # (The CLI smoke test seeds a generic HumanMessage; in production the job
    # function will seed a structured task message.)
    has_task_message = any(
        isinstance(m, HumanMessage) and state["company_name"] in m.content
        for m in state["messages"]
    )
    if not has_task_message:
        task_msg = HumanMessage(
            content=(
                f"Research this prospect company for B2B outreach:\n"
                f"Company: {state['company_name']}\n"
                f"Contact: {state.get('contact_name', 'unknown')}\n"
                f"Website: {state.get('company_url', 'unknown')}\n\n"
                f"Our product: {state['product_profile']}"
            )
        )
        messages = [system_prompt, task_msg] + state["messages"]

    ai_message: AIMessage = await _get_research_llm().ainvoke(messages)

    # If no tool calls remain, extract research text from content.
    if not ai_message.tool_calls:
        research_text: str = (
            ai_message.content
            if isinstance(ai_message.content, str)
            else str(ai_message.content)
        )
        return {
            "messages": [ai_message],
            "research_output": research_text,
        }

    # Tool calls pending — return the AIMessage and let ToolNode handle them.
    return {"messages": [ai_message]}


async def personalize_node(state: OutreachState) -> dict:
    """Write personalised email and LinkedIn outreach copy.

    Uses with_structured_output so this node does NOT use tools.
    The LLM directly returns an OutreachDraftOutput Pydantic object.
    """
    avoid = state.get("avoid_messaging", "").strip()
    avoid_clause = (
        f"\n\nSTRICT CONSTRAINT: Do not mention or imply any of the following "
        f"topics in any output: {avoid}. This constraint overrides all other instructions."
        if avoid
        else ""
    )

    system_prompt = SystemMessage(
        content=(
            "You are an expert B2B copywriter specialising in outbound sales. "
            "Write highly personalised, concise outreach that feels researched — "
            "not templated. Connect the prospect's specific situation to the "
            "seller's product capabilities.\n\n"
            "Guidelines:\n"
            "- Email subject: max 100 chars, no emojis, curiosity-inducing.\n"
            "- Email body: ~150-200 words, plain text, no HTML. Open with a "
            "  specific observation about the prospect, not a generic opener.\n"
            "- LinkedIn note: max 300 chars, friendly and direct.\n"
            "- data_confidence: 0.8+ only when specific signals were used. "
            "  If research is sparse, write strong semi-personalised copy from "
            "  industry and size alone — do NOT hallucinate specifics."
            + avoid_clause
        )
    )

    user_message = HumanMessage(
        content=(
            f"Write outreach for:\n"
            f"Company: {state['company_name']}\n"
            f"Contact: {state.get('contact_name', 'the decision maker')}\n\n"
            f"Our product profile:\n{state['product_profile']}\n\n"
            f"Research findings:\n{state['research_output']}"
        )
    )

    # with_structured_output returns the Pydantic object directly
    draft: OutreachDraftOutput = await _get_personalize_llm().ainvoke(
        [system_prompt, user_message]
    )

    return {
        "email_subject": draft.email_subject,
        "email_body": draft.email_body,
        "linkedin_note": draft.linkedin_note,
        "data_confidence": draft.data_confidence,
        "personalization_signals": draft.personalization_signals,
    }


async def schedule_node(state: OutreachState) -> dict:
    """ReAct scheduling agent.

    The LLM is bound with get_crm_pipeline. It will call that tool to check
    for existing pipeline entries, then reason about the best send time.
    When it has a final answer (no tool calls), the conditional edge routes
    to extract_schedule_node instead of looping back here.
    """
    system_prompt = SystemMessage(
        content=(
            "You are an outbound sales timing expert. Your job is to recommend "
            "the best time and channel to send B2B outreach to a prospect.\n\n"
            "Decision signals:\n"
            "1. Use get_crm_pipeline to check whether this prospect is already "
            "   in the pipeline. If they are, set flag_for_human = true.\n"
            "2. Infer the prospect's HQ timezone from their location. Recommend "
            "   sending on Tuesday, Wednesday, or Thursday between 9-11am local time.\n"
            "3. If the research shows recent funding or a product launch, increase "
            "   priority to 'high'.\n\n"
            "When you have gathered enough information, provide your final "
            "scheduling recommendation as structured text. Do not call get_crm_pipeline "
            "more than once."
        )
    )

    # Collect only the schedule-related messages from state (messages appended
    # after personalize_node completed).  We distinguish them by looking for
    # messages that were added after the initial research + personalisation phase.
    # For simplicity we pass the full message list — the LLM will use context
    # appropriately.
    task_message = HumanMessage(
        content=(
            f"Determine the best send time for outreach to:\n"
            f"Company: {state['company_name']}\n"
            f"Contact: {state.get('contact_name', 'the decision maker')}\n\n"
            f"Research summary:\n{state['research_output']}\n\n"
            f"Check the CRM pipeline, then provide your recommendation."
        )
    )

    # On the first call to schedule_node there are no prior schedule messages.
    # On subsequent calls (after tool results) the last few messages will be
    # tool call/result pairs — pass them so the LLM has context.
    prior_schedule_msgs = [
        m for m in state["messages"]
        if getattr(m, "name", None) in ("get_crm_pipeline",)
        or (hasattr(m, "tool_calls") and any(
            tc.get("name") == "get_crm_pipeline"
            for tc in (m.tool_calls if hasattr(m, "tool_calls") else [])
        ))
    ]

    messages = [system_prompt, task_message] + prior_schedule_msgs

    ai_message: AIMessage = await _get_schedule_llm().ainvoke(messages)
    return {"messages": [ai_message]}


async def extract_schedule_node(state: OutreachState) -> dict:
    """Extract structured ScheduleOutput from the completed schedule conversation.

    This node runs once — after schedule_node produces a final answer with no
    tool calls. It uses with_structured_output to parse the schedule reasoning
    into a strongly-typed ScheduleOutput, then serialises it to JSON for storage.
    """
    system_prompt = SystemMessage(
        content=(
            "Extract a structured send-time recommendation from the scheduling "
            "conversation below. Follow the field descriptions exactly. "
            "channel must always be 'email'. "
            "send_at must be a valid ISO 8601 datetime with timezone offset."
        )
    )

    # Feed the full message history — the final AIMessage from schedule_node
    # contains the reasoning we want to parse.
    messages = [system_prompt] + state["messages"]

    schedule: ScheduleOutput = await _get_schedule_extract_llm().ainvoke(messages)

    return {"schedule_output": schedule.model_dump_json()}


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def route_after_research(
    state: OutreachState,
) -> Literal["research_tools_node", "personalize_node"]:
    """Route to tool execution if the last message has tool calls, else proceed."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "research_tools_node"
    return "personalize_node"


def route_after_schedule(
    state: OutreachState,
) -> Literal["schedule_tools_node", "extract_schedule_node"]:
    """Route to tool execution if the last message has tool calls, else extract."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "schedule_tools_node"
    return "extract_schedule_node"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

builder = StateGraph(OutreachState)

# Register nodes
builder.add_node("research_node", research_node)
builder.add_node("research_tools_node", research_tools_node)
builder.add_node("personalize_node", personalize_node)
builder.add_node("schedule_node", schedule_node)
builder.add_node("schedule_tools_node", schedule_tools_node)
builder.add_node("extract_schedule_node", extract_schedule_node)

# Entry point
builder.add_edge(START, "research_node")

# Research ReAct loop
builder.add_conditional_edges(
    "research_node",
    route_after_research,
    {
        "research_tools_node": "research_tools_node",
        "personalize_node": "personalize_node",
    },
)
builder.add_edge("research_tools_node", "research_node")

# Personalisation → scheduling
builder.add_edge("personalize_node", "schedule_node")

# Schedule ReAct loop
builder.add_conditional_edges(
    "schedule_node",
    route_after_schedule,
    {
        "schedule_tools_node": "schedule_tools_node",
        "extract_schedule_node": "extract_schedule_node",
    },
)
builder.add_edge("schedule_tools_node", "schedule_node")

# Final extraction → END
builder.add_edge("extract_schedule_node", END)

# Compile — recursion_limit is set at ainvoke/astream call time, not here
graph = builder.compile()
