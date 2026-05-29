import json

import httpx
from langchain_core.tools import tool

from app.config import settings


@tool
async def web_search(query: str, n_results: int = 5) -> str:
    """Search the web for information about a company or topic.

    Use this tool to find firmographic data, recent news, funding rounds,
    product launches, and other signals about a prospect company. Prefer
    specific queries over broad ones to conserve search quota.

    Args:
        query: The search query string.
        n_results: Number of results to return (default 5, max 10).

    Returns:
        A formatted string of search results including title, snippet, and
        URL for each result. Returns an error string on failure.
    """
    n_results = min(n_results, 10)
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": n_results}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return f"SEARCH_FAILED: HTTP {exc.response.status_code} — {exc}"
    except Exception as exc:
        return f"SEARCH_FAILED: {exc}"

    results: list[str] = []

    # Organic results
    for item in data.get("organic", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        results.append(f"Title: {title}\nSnippet: {snippet}\nURL: {link}")

    # News results (if present)
    for item in data.get("news", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        date = item.get("date", "")
        results.append(f"[NEWS] Title: {title}\nDate: {date}\nSnippet: {snippet}\nURL: {link}")

    if not results:
        return "No results found."

    return "\n\n---\n\n".join(results)
