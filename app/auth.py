from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.database import get_db
from app.models import User, OTPCode
from app.schemas import UserCreate, UserResponse, OTPVerify, Token
from app.email import send_otp_email, generate_otp
from app.config import settings

router = APIRouter()

# تنظیمات هش کردن پسورد
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

@router.post("/register", response_model=dict)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # بررسی وجود کاربر
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="این ایمیل قبلاً ثبت شده است"
        )
    
    # ایجاد کاربر جدید
    hashed_password = get_password_hash(user.password)
    db_user = User(
        email=user.email,
        hashed_password=hashed_password,
        is_active=False,  # کاربر تا تأیید OTP فعال نیست
        is_verified=False
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # تولید و ارسال کد OTP
    otp_code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    
    # ذخیره OTP در دیتابیس
    db_otp = OTPCode(
        email=user.email,
        code=otp_code,
        expires_at=expires_at
    )
    db.add(db_otp)
    db.commit()
    
    # ارسال ایمیل
    if send_otp_email(user.email, otp_code):
        return {
            "message": "ثبت‌نام موفقیت‌آمیز بود. لطفاً ایمیل خود را برای کد تأیید بررسی کنید.",
            "email": user.email
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="خطا در ارسال ایمیل"
        )

@router.post("/verify-otp", response_model=dict)
def verify_otp(otp_data: OTPVerify, db: Session = Depends(get_db)):
    # پیدا کردن کد OTP
    db_otp = db.query(OTPCode).filter(
        OTPCode.email == otp_data.email,
        OTPCode.code == otp_data.code,
        OTPCode.is_used == False,
        OTPCode.expires_at > datetime.utcnow()
    ).first()
    
    if not db_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="کد تأیید نامعتبر یا منقضی شده است"
        )
    
    # علامت‌گذاری کد به عنوان استفاده شده
    db_otp.is_used = True
    
    # فعال کردن کاربر
    user = db.query(User).filter(User.email == otp_data.email).first()
    if user:
        user.is_active = True
        user.is_verified = True
    
    db.commit()
    
    return {"message": "حساب کاربری با موفقیت تأیید شد"}

@router.post("/login", response_model=Token)
def login(user: UserCreate, db: Session = Depends(get_db)):
    # پیدا کردن کاربر
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ایمیل یا رمز عبور نادرست است"
        )
    
    if not db_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لطفاً ابتدا حساب کاربری خود را با کد تأیید فعال کنید"
        )
    
    # ایجاد توکن دسترسی
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/resend-otp", response_model=dict)
def resend_otp(otp_data: OTPVerify, db: Session = Depends(get_db)):
    # بررسی وجود کاربر
    user = db.query(User).filter(User.email == otp_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="کاربری با این ایمیل یافت نشد"
        )
    
    # تولید کد OTP جدید
    otp_code = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    
    # ذخیره OTP جدید
    db_otp = OTPCode(
        email=otp_data.email,
        code=otp_code,
        expires_at=expires_at
    )
    db.add(db_otp)
    db.commit()
    
    # ارسال ایمیل
    if send_otp_email(otp_data.email, otp_code):
        return {"message": "کد تأیید جدید ارسال شد"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="خطا در ارسال ایمیل"
        )