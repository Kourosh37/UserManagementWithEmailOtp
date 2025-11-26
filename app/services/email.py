import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anyio

from app.core.config import settings


async def send_otp_email(email: str, otp_code: str) -> tuple[bool, str | None]:
    def _send() -> None:
        if not all([settings.SMTP_SERVER, settings.SMTP_USERNAME, settings.SMTP_PASSWORD, settings.FROM_EMAIL]):
            raise RuntimeError("SMTP settings are incomplete.")

        message = MIMEMultipart()
        message["From"] = settings.FROM_EMAIL or os.getenv("FROM_EMAIL")
        message["To"] = email
        message["Subject"] = "Your verification code"

        body = f"""
        <div>
            <h2>Email verification code</h2>
            <p>Use the following one-time code to verify your account:</p>
            <h3 style="color: #2563eb; font-size: 24px; text-align: center;">{otp_code}</h3>
            <p>The code expires in {settings.OTP_EXPIRE_SECONDS // 60} minutes.</p>
        </div>
        """
        message.attach(MIMEText(body, "html"))

        with smtplib.SMTP(settings.SMTP_SERVER, int(settings.SMTP_PORT), timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)

    try:
        await anyio.to_thread.run_sync(_send)
        return True, None
    except Exception as exc:  # pragma: no cover - SMTP network path
        print(f"[email] Failed to send OTP email: {exc}")
        return False, str(exc)
