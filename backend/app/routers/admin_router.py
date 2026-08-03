"""GET /admin/* — 운영자 전용. 고객 목록(필터+페이지네이션)과 KPI 요약, 고객별 액션 발송."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.auth import require_staff
from db import get_engine
from app.schemas import ActionRequest, CustomerListResponse, KpiResponse

router = APIRouter()

VALID_ACTION_TYPES = {"reminder", "discount_offer"}


@router.get("/customers", response_model=CustomerListResponse)
def list_customers(
    risk_tier: Optional[str] = Query(None, description="고위험 | 저위험"),
    segment: Optional[str] = Query(None, description="예: 고위험/고가치"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: dict = Depends(require_staff),
):
    conditions, params = [], {}
    if risk_tier:
        conditions.append("risk_tier = :risk_tier")
        params["risk_tier"] = risk_tier
    if segment:
        conditions.append("segment = :segment")
        params["segment"] = segment
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM customer_churn_scores {where}"), params).scalar()
        rows = conn.execute(
            text(
                f"SELECT * FROM customer_churn_scores {where} "
                "ORDER BY churn_proba DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        ).mappings().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [dict(r) for r in rows],
    }


@router.get("/kpis", response_model=KpiResponse)
def kpis(_: dict = Depends(require_staff)):
    engine = get_engine()
    with engine.connect() as conn:
        model_stats = conn.execute(text("SELECT * FROM model_stats")).mappings().all()
        shap_importance = conn.execute(
            text("SELECT * FROM shap_importance ORDER BY mean_abs_shap DESC")
        ).mappings().all()
        funnel_stats = conn.execute(text("SELECT * FROM funnel_stats")).mappings().all()
        segment_drivers = conn.execute(
            text("SELECT * FROM segment_drivers ORDER BY pct DESC")
        ).mappings().all()
        retention_cohort = conn.execute(
            text("SELECT * FROM retention_cohort ORDER BY cohort_month, month_offset")
        ).mappings().all()

    return {
        "model_stats": [dict(r) for r in model_stats],
        "shap_importance": [dict(r) for r in shap_importance],
        "funnel_stats": [dict(r) for r in funnel_stats],
        "segment_drivers": [dict(r) for r in segment_drivers],
        "retention_cohort": [dict(r) for r in retention_cohort],
    }


@router.post("/customers/{msno}/actions")
def send_customer_action(msno: str, body: ActionRequest, staff: dict = Depends(require_staff)):
    """관리자가 특정 고객에게 리마인드/할인 오퍼를 "발송"한 것으로 기록.
    실제 이메일/푸시 발송은 하지 않고, DB에 기록만 남긴다 — 그 msno로 고객 로그인하면
    /me/actions에서 이 기록을 조회해 소비자 앱 알림함에 보여준다."""
    if body.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail="action_type은 reminder 또는 discount_offer여야 합니다")

    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT msno FROM customer_churn_scores WHERE msno = :msno"), {"msno": msno}
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="존재하지 않는 msno입니다")
        conn.execute(
            text(
                "INSERT INTO customer_actions (msno, action_type, sent_by) "
                "VALUES (:msno, :action_type, :sent_by)"
            ),
            {"msno": msno, "action_type": body.action_type, "sent_by": staff.get("sub")},
        )

    return {"status": "sent", "msno": msno, "action_type": body.action_type}
