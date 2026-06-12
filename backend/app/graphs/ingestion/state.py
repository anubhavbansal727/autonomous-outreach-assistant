"""IngestionState — shared state TypedDict for the Ingestion LangGraph.

In plain English:
- The shared "clipboard" for the ingestion graph's two steps.
- ``url`` goes in; ``scrape_node`` fills ``scraped_pages``; ``extract_node``
  fills ``product_profile_output`` (or ``error`` if something went wrong).
- ``ScrapedPage`` records each page we tried, including whether it succeeded.
"""

from typing import TypedDict

from pydantic import BaseModel


class ScrapedPage(BaseModel):
    url: str
    content: str
    scraped: bool


class IngestionState(TypedDict):
    url: str
    scraped_pages: list[ScrapedPage]
    product_profile_output: dict | None   # serialised ProductProfileOutput
    error: str | None
