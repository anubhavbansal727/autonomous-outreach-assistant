"""BatchState — shared state for the batch multi-prospect LangGraph.

In plain English:
- The shared "clipboard" for the batch graph. ``prospects`` is the to-do list
  (one ``ResearchTask`` per CSV row); ``research_results`` is where finished
  research lands.
- ``research_results`` uses ``Annotated[..., operator.add]`` so each parallel
  research branch APPENDS its one result instead of overwriting the list — that
  is how many parallel branches safely merge their output back together.

The batch graph fans out research across all prospects in parallel via the
Send() API, then runs personalisation sequentially at fan-in. Per-branch
research outputs accumulate into ``research_results`` via the operator.add
reducer so the sequential personalisation node sees every prospect.
"""

import operator
from typing import Annotated, TypedDict


class ResearchTask(TypedDict):
    """Payload dispatched to each parallel research branch via Send()."""

    index: int
    job_id: str
    company_name: str
    contact_name: str
    # Shared across all prospects — carried in each Send payload so the
    # research branch can build a full OutreachState without main-graph access.
    batch_id: str
    product_profile: str        # JSON string of the user's product profile
    avoid_messaging: str


class ResearchResult(TypedDict):
    index: int
    job_id: str
    company_name: str
    contact_name: str
    research_output: str


class BatchState(TypedDict):
    # Input — provided by the caller before graph.astream()
    batch_id: str
    product_profile: str        # JSON string of the user's product profile
    avoid_messaging: str
    prospects: list[ResearchTask]

    # Fan-in accumulator — each parallel research branch appends one result.
    research_results: Annotated[list[ResearchResult], operator.add]
