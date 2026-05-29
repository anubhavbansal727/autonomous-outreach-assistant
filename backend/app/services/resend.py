import asyncio
from functools import partial

import resend as resend_sdk

from app.config import settings


def _build_html(body_text: str) -> str:
    """Convert plain-text email body to minimal HTML.

    Preserves paragraph breaks (double newline → <p>) and single newlines
    (→ <br>) without introducing inline styles or extra markup.
    """
    paragraphs = body_text.split("\n\n")
    html_parts = []
    for para in paragraphs:
        inner = para.strip().replace("\n", "<br>")
        if inner:
            html_parts.append(f"<p>{inner}</p>")
    return "\n".join(html_parts)


async def send_email(
    to_email: str,
    from_name: str,
    resend_domain: str,
    subject: str,
    body_text: str,
) -> str:
    """Send a CAN-SPAM–compliant email via the Resend API.

    CAN-SPAM / RFC 8058 compliance:
    - List-Unsubscribe: mailto URI so recipients can opt out via their MUA.
    - List-Unsubscribe-Post: "List-Unsubscribe=One-Click" enables one-click
      unsubscribe in Gmail/Outlook without opening a browser (RFC 8058).
    - X-Entity-Ref-ID: per-recipient ID for bounce and complaint attribution.

    The Resend SDK call is synchronous (single HTTP request). We offload it
    to a thread-pool executor so we do not block the async event loop.

    Returns the Resend message ID on success. Raises on any API failure.
    """
    resend_sdk.api_key = settings.RESEND_API_KEY

    payload = {
        "from": f"{from_name} <outreach@{resend_domain}>",
        "to": [to_email],
        "subject": subject,
        "text": body_text,
        "html": _build_html(body_text),
        "headers": {
            # CAN-SPAM: unsubscribe mailto link visible in MUA header
            "List-Unsubscribe": f"<mailto:unsubscribe@{resend_domain}?subject=unsubscribe>",
            # RFC 8058: one-click unsubscribe (required by Gmail/Yahoo 2024+)
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            # Bounce attribution
            "X-Entity-Ref-ID": to_email,
        },
    }

    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, partial(resend_sdk.Emails.send, payload))
    return response["id"]
