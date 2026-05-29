from langchain_core.tools import tool
from playwright.async_api import async_playwright


@tool
async def scrape_website(url: str) -> str:
    """Scrape the visible text content of a website from a given URL.

    Use this tool to read a company's homepage, product pages, or any
    public URL that may contain useful prospect information. Returns the
    first 10,000 characters of the page body text.

    Args:
        url: The full URL to scrape, including the scheme (https://).

    Returns:
        The inner text of the page body, truncated to 10,000 characters,
        or a SCRAPE_FAILED string on error.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=15000, wait_until="networkidle")
                content = await page.inner_text("body")
            finally:
                await browser.close()
        return content[:10000]
    except Exception as exc:
        return f"SCRAPE_FAILED: {url} — {exc}"
