import asyncio

from app.graphs.ingestion.graph import graph
from app.graphs.ingestion.state import IngestionState


async def main() -> None:
    state: IngestionState = {
        "url": "https://linear.app",
        "scraped_pages": [],
        "product_profile_output": None,
        "error": None,
    }
    result = await graph.ainvoke(state, config={"recursion_limit": 5})
    print("\n=== SCRAPED PAGES ===")
    for p in result["scraped_pages"]:
        status = "OK" if p.scraped else "FAILED"
        print(f"  [{status}] {p.url} ({len(p.content)} chars)")
    print("\n=== PRODUCT PROFILE ===")
    import json
    print(json.dumps(result["product_profile_output"], indent=2))
    if result["error"]:
        print("\n=== ERROR ===")
        print(result["error"])


if __name__ == "__main__":
    asyncio.run(main())
