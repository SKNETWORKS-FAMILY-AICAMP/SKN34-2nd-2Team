"""Pydantic 응답/요청 모델 — API 계약을 여기 한 곳에 모아둔다."""
import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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


class CampaignAudienceRequest(BaseModel):
    purpose: Literal["retention", "renewal", "winback"]
    action_type: Literal["reminder", "discount_offer"]
    risk_tier: Optional[Literal["고위험", "저위험"]] = None
    segment: Optional[
        Literal[
            "고위험/고가치",
            "고위험/저가치",
            "저위험/고가치",
            "저위험/저가치",
        ]
    ] = None
    selection_mode: Literal["all_matching", "top_n", "manual"] = "all_matching"
    audience_limit: Optional[int] = Field(default=None, ge=1, le=50000)
    exclude_recent_days: int = Field(default=7, ge=0, le=365)
    manual_msnos: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("manual_msnos")
    @classmethod
    def normalize_manual_msnos(cls, values: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for value in values:
            msno = value.strip()
            if msno and msno not in seen:
                normalized.append(msno)
                seen.add(msno)
        return normalized

    @model_validator(mode="after")
    def validate_selection(self):
        if self.selection_mode == "top_n" and self.audience_limit is None:
            raise ValueError("상위 N명 선택에서는 audience_limit이 필요합니다")
        if self.selection_mode == "manual" and not self.manual_msnos:
            raise ValueError("직접 선택 방식에서는 고객을 1명 이상 추가해야 합니다")
        return self


class CampaignPreviewRequest(CampaignAudienceRequest):
    pass


class CampaignCreateRequest(CampaignAudienceRequest):
    request_key: str = Field(min_length=8, max_length=64)
    name: str = Field(min_length=2, max_length=120)


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
    lifecycle_status: Optional[str] = None
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


class ActionsSummaryResponse(BaseModel):
    total: int
    by_type: list[dict]
    by_segment: list[dict]
    recent: list[dict]


class CampaignPreviewResponse(BaseModel):
    requested_count: int
    matched_count: int
    excluded_condition_count: int
    excluded_recent_count: int
    eligible_count: int
    selected_count: int
    launchable: bool
    warning: Optional[str] = None
    sample: list[CustomerRisk]


class CampaignResponse(BaseModel):
    id: int
    request_key: str
    name: str
    purpose: str
    action_type: str
    lifecycle_status: str
    risk_tier: Optional[str] = None
    segment: Optional[str] = None
    selection_mode: str
    audience_limit: Optional[int] = None
    exclude_recent_days: int
    matched_count: int
    excluded_count: int
    recipient_count: int
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    launched_at: Optional[datetime] = None
