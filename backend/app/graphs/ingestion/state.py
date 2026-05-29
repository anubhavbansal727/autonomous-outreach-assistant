"""IngestionState — shared state TypedDict for the Ingestion LangGraph."""

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
