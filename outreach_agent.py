import os
import resend
from dotenv import load_dotenv

load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

resend.api_key = os.getenv("RESEND_API_KEY")


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Dispatches outreach email via the Resend API."""
    if not resend.api_key:
        print("[X] Resend error: RESEND_API_KEY environment variable is not set.")
        return False

    sender_email = os.getenv("RESEND_FROM", "Nomadik Security <onboarding@resend.dev>")

    params = {
        "from": sender_email,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }

    try:
        response = resend.Emails.send(params)
        email_id = (
            response.get("id")
            if isinstance(response, dict)
            else getattr(response, "id", None)
        )
        print(f"[+] Resend dispatch successful! Email ID: {email_id}")
        return True
    except Exception as e:
        print(f"[X] Resend dispatch failed: {e}")
        return False


if __name__ == "__main__":
    test_recipient = os.getenv("TEST_RECIPIENT", "kalen.vandenbos@gmail.com")
    print(f"[*] Testing Resend delivery to {test_recipient}...")
    send_email(
        test_recipient,
        "Test Pitch Delivery",
        "This is a test message from Nomadik Security Operations.",
    )
