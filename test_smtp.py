"""Quick SMTP connectivity test script using credentials from .env."""

import os
import smtplib

from dotenv import load_dotenv

load_dotenv()


def test_smtp_simple() -> bool:
    """Attempt to authenticate and quit gracefully to confirm SMTP settings."""

    try:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")

        print("Testing basic SMTP connection...")

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.quit()

        print("SMTP connection successful.")
        return True

    except Exception as exc:  # pragma: no cover - diagnostic helper
        print(f"SMTP error: {exc}")
        return False


if __name__ == "__main__":
    test_smtp_simple()
