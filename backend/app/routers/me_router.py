"""GET /me/risk — 로그인한 고객(msno) 본인의 위험도/LTV 1건 조회. 소비자 앱 3개 화면이 이 응답 하나로 구성됨.
GET /me/actions — 관리자가 나(msno)에게 보낸 리마인드/할인 오퍼 내역 조회."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import require_customer
from db import get_engine
from app.schemas import ActionRecord, CustomerRisk

router = APIRouter()


@router.get("/risk", response_model=CustomerRisk)
def my_risk(payload: dict = Depends(require_customer)):
    msno = payload["sub"]
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM customer_churn_scores WHERE msno = :msno"), {"msno": msno}
        ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="해당 msno의 스코어링 데이터가 없습니다")
    return dict(row)


@router.get("/actions", response_model=list[ActionRecord])
def my_actions(payload: dict = Depends(require_customer)):
    msno = payload["sub"]
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, msno, action_type, sent_by, sent_at FROM customer_actions "
                "WHERE msno = :msno ORDER BY sent_at DESC"
            ),
            {"msno": msno},
        ).mappings().all()
    return [dict(r) for r in rows]
