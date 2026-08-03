"""Pydantic 응답/요청 모델 — API 계약을 여기 한 곳에 모아둔다."""
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator

# 회원가입 비밀번호 규칙: 8자 이상 + 특수문자 1개 이상 포함.
_SPECIAL_CHAR_RE = re.compile(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]/\\~`;']")


# ---- 요청 ----
class StaffSignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("비밀번호는 8자 이상이어야 합니다")
        if not _SPECIAL_CHAR_RE.search(v):
            raise ValueError("비밀번호에 특수문자를 1개 이상 포함해야 합니다 (예: ! @ # $ %)")
        return v


class StaffLoginRequest(BaseModel):
    email: str
    password: str


class CustomerLoginRequest(BaseModel):
    msno: str


class ActionRequest(BaseModel):
    action_type: str  # "reminder" | "discount_offer"


# ---- 응답 ----
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class CustomerRisk(BaseModel):
    msno: str
    churn_proba: float
    risk_tier: str
    ltv_tier: str
    segment: str
    avg_monthly_revenue: Optional[float] = None
    expected_lifetime_months: Optional[float] = None
    ltv_approx: Optional[float] = None
    days_to_expire: Optional[int] = None
    days_since_last_txn: Optional[int] = None
    scored_at: Optional[date] = None


class CustomerListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CustomerRisk]


class KpiResponse(BaseModel):
    model_stats: list[dict]
    shap_importance: list[dict]
    funnel_stats: list[dict]
    segment_drivers: list[dict]
    retention_cohort: list[dict]


class ActionRecord(BaseModel):
    id: int
    msno: str
    action_type: str
    sent_by: Optional[str] = None
    sent_at: datetime
