import resend as resend_sdk

from app.config import settings


async def send_email(
    to_email: str,
    from_name: str,
    resend_domain: str,
    subject: str,
    body_text: str,
) -> str:
    """Send an email via the Resend API.

    Returns the Resend message id on success. Raises on any API failure.
    The function is declared async for consistency with the async codebase;
    the Resend SDK call itself is synchronous but fast (single HTTP request).
    """
    resend_sdk.api_key = settings.RESEND_API_KEY

    html_body = "<br>".join(body_text.splitlines())
    html_body = f"<p>{html_body}</p>"

    response = resend_sdk.Emails.send(
        {
            "from": f"{from_name} <outreach@{resend_domain}>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
            "headers": {
                "List-Unsubscribe": f"<mailto:unsubscribe@{resend_domain}>",
                "X-Entity-Ref-ID": to_email,
            },
        }
    )
    return response["id"]
