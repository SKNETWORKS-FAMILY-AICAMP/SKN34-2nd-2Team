"""
인증 유틸 — 비밀번호 해싱 + JWT 발급/검증.

두 종류의 토큰을 발급한다:
  - {"type": "staff", "sub": email, "role": "admin"|"staff"}    -> 운영자
  - {"type": "customer", "sub": msno}                            -> 고객(체험 로그인)
require_staff / require_customer 의존성으로 라우터에서 구분해서 막는다.
"""
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

# 실제 운영에선 .env에 JWT_SECRET을 반드시 채워넣으세요 (기본값은 로컬 개발용 임시값).
SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_token(payload: dict, expires_hours: int = 8) -> str:
    data = payload.copy()
    data["exp"] = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않거나 만료된 토큰입니다")


def require_staff(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    payload = decode_token(creds.credentials)
    if payload.get("type") != "staff":
        raise HTTPException(status_code=403, detail="운영자 권한이 필요합니다")
    return payload


def require_customer(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> dict:
    payload = decode_token(creds.credentials)
    if payload.get("type") != "customer":
        raise HTTPException(status_code=403, detail="고객 인증이 필요합니다")
    return payload
