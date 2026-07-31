"""POST /auth/* — 운영자 회원가입/로그인, 고객 체험 로그인."""
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.auth import create_token, hash_password, verify_password
from db import get_engine
from app.schemas import CustomerLoginRequest, StaffLoginRequest, StaffSignupRequest, TokenResponse

router = APIRouter()


@router.post("/staff-signup", response_model=TokenResponse)
def staff_signup(body: StaffSignupRequest):
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM staff_accounts WHERE email = :email"), {"email": body.email}
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="이미 가입된 이메일입니다")
        conn.execute(
            text(
                "INSERT INTO staff_accounts (email, password_hash, name, role) "
                "VALUES (:email, :pw, :name, 'staff')"
            ),
            {"email": body.email, "pw": hash_password(body.password), "name": body.name},
        )
    token = create_token({"sub": body.email, "type": "staff", "role": "staff"})
    return TokenResponse(access_token=token, role="staff")


@router.post("/staff-login", response_model=TokenResponse)
def staff_login(body: StaffLoginRequest):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM staff_accounts WHERE email = :email"), {"email": body.email}
        ).mappings().first()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")
    token = create_token({"sub": row["email"], "type": "staff", "role": row["role"]})
    return TokenResponse(access_token=token, role=row["role"])


@router.post("/customer-demo-login", response_model=TokenResponse)
def customer_demo_login(body: CustomerLoginRequest):
    """실제 비밀번호 없음 — customer_churn_scores에 존재하는 msno인지만 확인하고 체험 토큰 발급."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT msno FROM customer_churn_scores WHERE msno = :msno"), {"msno": body.msno}
        ).first()
    if not row:
        raise HTTPException(status_code=404, detail="존재하지 않는 msno입니다")
    token = create_token({"sub": body.msno, "type": "customer"})
    return TokenResponse(access_token=token, role="customer")
