"""IngestionGraph — LangGraph StateGraph for product profile extraction.

In plain English (read this first):
- This is the simplest graph: just two steps in a straight line, no loops.
- ``scrape_node``: visit a few standard pages of the user's website
  (home, /pricing, /about, /customers, /case-studies) and grab their text.
  This is plain Playwright code — no AI.
- ``extract_node``: feed all that text to GPT-4o and have it fill in a
  structured product profile (name, one-liner, pain points, etc.). It uses
  ``with_structured_output`` so the answer comes back as a typed object, and it
  is told to NOT invent details and to list whatever it couldn't find.
- The result becomes the ProductProfile the user can save and then use for
  every outreach email.

Graph topology
--------------

    START
      │
      ▼
  scrape_node  (pure Python, no LLM — Playwright)
      │
      ▼
  extract_node  (GPT-4o, temp=0.2, with_structured_output)
      │
      ▼
     END

Rules (enforced by CLAUDE.md)
------------------------------
- scrape_node uses async_playwright directly (no @tool wrapper).
- extract_node uses llm.with_structured_output() — never output_json.
- LLM is lazily initialised so the module imports without OPENAI_API_KEY.
- No YAML, no CrewAI patterns, no conditional edges needed here.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from .state import IngestionState, ScrapedPage


# ---------------------------------------------------------------------------
# Structured output schema — also exported for use in ARQ jobs and routers
# ---------------------------------------------------------------------------


class ProductProfileOutput(BaseModel):
    product_name: str
    one_liner: str | None = None
    target_customer: str | None = None
    pain_points: list[str] = []
    differentiators: list[str] = []
    case_studies: list[str] = []
    cta: str | None = None
    icp: str | None = None
    extraction_confidence: str = "low"   # "low" | "medium" | "high"
    missing_fields: list[str] = []


# ---------------------------------------------------------------------------
# LLM instance — lazily initialised to allow import without OPENAI_API_KEY
# ---------------------------------------------------------------------------

_extract_llm = None


def _get_extract_llm() -> ChatOpenAI:
    global _extract_llm
    if _extract_llm is None:
        _extract_llm = ChatOpenAI(
            model="gpt-4o", temperature=0.2, api_key=settings.OPENAI_API_KEY
        ).with_structured_output(ProductProfileOutput)
    return _extract_llm


# ---------------------------------------------------------------------------
# URL paths to scrape for each submitted domain
# ---------------------------------------------------------------------------

_PATHS_TO_SCRAPE: list[str] = [
    "/",
    "/pricing",
    "/about",
    "/customers",
    "/case-studies",
]

_CONTENT_TRUNCATE_CHARS = 5_000


def _build_full_url(base_url: str, path: str) -> str:
    """Combine a base URL with a path, stripping any trailing slash from base."""
    base = base_url.rstrip("/")
    return f"{base}{path}"


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


async def scrape_node(state: IngestionState) -> dict:
    """Scrape multiple pages of the submitted URL using Playwright.

    Uses a single browser instance for all pages. Errors and 404s are
    silently skipped — the page is recorded with scraped=False and content="".
    """
    from playwright.async_api import async_playwright  # local import keeps top-level import clean

    base_url = state["url"]
    pages_result: list[ScrapedPage] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for path in _PATHS_TO_SCRAPE:
                full_url = _build_full_url(base_url, path)
                page = await browser.new_page()
                try:
                    response = await page.goto(full_url, timeout=15_000)
                    # Treat non-2xx as a failure (catches 404, 403, etc.)
                    if response is None or response.status >= 400:
                        pages_result.append(
                            ScrapedPage(url=full_url, content="", scraped=False)
                        )
                    else:
                        raw_text: str = await page.inner_text("body")
                        truncated = raw_text[:_CONTENT_TRUNCATE_CHARS]
                        pages_result.append(
                            ScrapedPage(url=full_url, content=truncated, scraped=True)
                        )
                except Exception:
                    # Network errors, navigation timeouts, etc.
                    pages_result.append(
                        ScrapedPage(url=full_url, content="", scraped=False)
                    )
                finally:
                    await page.close()
        finally:
            await browser.close()

    return {"scraped_pages": pages_result}


async def extract_node(state: IngestionState) -> dict:
    """Extract structured product profile from scraped page content using GPT-4o.

    Concatenates all successfully scraped pages into a single context string,
    then calls the LLM with with_structured_output to populate ProductProfileOutput.
    On ValidationError a partial model is constructed via model_construct() and
    the error message is stored in state["error"].
    """
    scraped_pages = state["scraped_pages"]

    # Build concatenated context from pages that scraped successfully
    context_parts: list[str] = []
    for sp in scraped_pages:
        if sp.scraped and sp.content:
            context_parts.append(f"\n\n---PAGE: {sp.url}---\n\n{sp.content}")

    context_text = "".join(context_parts).strip()

    if not context_text:
        # Nothing was scraped — return a minimal failed profile
        empty_profile = ProductProfileOutput.model_construct(
            product_name="Unknown",
            extraction_confidence="low",
            missing_fields=[
                "product_name",
                "one_liner",
                "target_customer",
                "pain_points",
                "differentiators",
                "case_studies",
                "cta",
                "icp",
            ],
        )
        return {
            "product_profile_output": empty_profile.model_dump(),
            "error": "No pages could be scraped — all paths returned errors or timed out.",
        }

    system_prompt = SystemMessage(
        content=(
            "You are a B2B SaaS product positioning expert. "
            "Extract structured product profile information from marketing copy.\n\n"
            "Guidelines:\n"
            "- Populate every field you can infer confidently from the provided text.\n"
            "- Add any field name you CANNOT infer to missing_fields (use the exact "
            "  field name as it appears in the schema).\n"
            "- Never hallucinate details that are not present or strongly implied by "
            "  the source text.\n"
            "- Set extraction_confidence to:\n"
            "    'high'   — most fields populated, rich marketing copy available\n"
            "    'medium' — key fields populated but several are missing\n"
            "    'low'    — minimal content available, most fields missing\n"
            "- pain_points, differentiators, case_studies: return as lists of concise "
            "  strings, not prose paragraphs."
        )
    )

    user_message = HumanMessage(
        content=(
            f"Extract the product profile from the following marketing copy:\n\n"
            f"{context_text}"
        )
    )

    try:
        profile: ProductProfileOutput = await _get_extract_llm().ainvoke(
            [system_prompt, user_message]
        )
        return {
            "product_profile_output": profile.model_dump(),
            "error": None,
        }
    except ValidationError as exc:
        # Build a partial model so downstream consumers have something to work with
        partial_profile = ProductProfileOutput.model_construct(
            product_name="Unknown",
            extraction_confidence="low",
            missing_fields=["validation_failed"],
        )
        return {
            "product_profile_output": partial_profile.model_dump(),
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

builder = StateGraph(IngestionState)

builder.add_node("scrape_node", scrape_node)
builder.add_node("extract_node", extract_node)

builder.add_edge(START, "scrape_node")
builder.add_edge("scrape_node", "extract_node")
builder.add_edge("extract_node", END)

# Compile — recursion_limit is set at ainvoke/astream call time, not here
graph = builder.compile()
