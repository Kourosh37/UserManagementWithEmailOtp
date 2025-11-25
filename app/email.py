import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import random
import string

load_dotenv()

def generate_otp(length: int = 6) -> str:
    """تولید کد OTP تصادفی"""
    return ''.join(random.choices(string.digits, k=length))

def send_otp_email(email: str, otp_code: str):
    """ارسال ایمیل حاوی کد OTP"""
    
    # برای تست در حالت توسعه
    if os.getenv("ENVIRONMENT") == "development":
        print("=" * 50)
        print(f"📧 ایمیل تست - به: {email}")
        print(f"🔢 کد OTP: {otp_code}")
        print("=" * 50)
        return True
    
    # ایجاد محتوای ایمیل
    subject = "کد تأیید حساب کاربری شما"
    body = f"""
    <div dir="rtl">
        <h2>کد تأیید حساب کاربری</h2>
        <p>کاربر گرامی،</p>
        <p>کد تأیید حساب کاربری شما:</p>
        <h3 style="color: #2563eb; font-size: 24px; text-align: center;">{otp_code}</h3>
        <p>این کد تا 10 دقیقه معتبر است.</p>
        <p>اگر این درخواست توسط شما صادر نشده است، لطفاً این ایمیل را نادیده بگیرید.</p>
    </div>
    """
    
    try:
        # ایجاد پیام ایمیل
        message = MIMEMultipart()
        message["From"] = os.getenv("FROM_EMAIL")
        message["To"] = email
        message["Subject"] = subject
        
        # اضافه کردن محتوا
        message.attach(MIMEText(body, "html"))
        
        # اتصال به سرور SMTP و ارسال ایمیل
        with smtplib.SMTP(os.getenv("SMTP_SERVER"), int(os.getenv("SMTP_PORT"))) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD"))
            server.send_message(message)
        
        print(f"✅ کد OTP به {email} ارسال شد")
        return True
        
    except Exception as e:
        print(f"❌ خطا در ارسال ایمیل: {e}")
        return False
