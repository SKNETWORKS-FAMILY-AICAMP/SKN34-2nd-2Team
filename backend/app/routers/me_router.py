"""GET /me/risk — 로그인한 고객(msno) 본인의 위험도/LTV 1건 조회. 소비자 앱 3개 화면이 이 응답 하나로 구성됨.
GET /me/actions — 관리자가 나(msno)에게 보낸 리마인드/할인 오퍼 내역 + 내가 직접 받은 혜택 조회.
PATCH /me/actions/{id}/read, POST /me/actions/read-all — 알림 읽음 처리(뱃지 숫자 반영용).
POST /me/benefits/claim — 콘서트 티켓 추첨 응모, 연차 혜택/갱신 즉시 리워드 셀프 수령."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import require_customer
from db import get_engine
from app.schemas import ActionRecord, BenefitClaimRequest, CustomerRisk

router = APIRouter()

# 혜택별 안내 문구 — customer_actions.sent_by에 남겨서 관리자 콘솔/DB에서도 무슨 혜택인지 바로 보이게 한다.
BENEFIT_LABELS = {
    "concert_raffle": "콘서트 티켓 추첨 응모",
    "annual_tier": "연 단위 유지 혜택 수령",
    "renewal_reward": "갱신 즉시 리워드 수령",
}


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
                "SELECT id, msno, action_type, is_read, benefit_key, sent_by, sent_at FROM customer_actions "
                "WHERE msno = :msno ORDER BY sent_at DESC"
            ),
            {"msno": msno},
        ).mappings().all()
    return [dict(r) for r in rows]


@router.patch("/actions/{action_id}/read", response_model=ActionRecord)
def mark_action_read(action_id: int, payload: dict = Depends(require_customer)):
    msno = payload["sub"]
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM customer_actions WHERE id = :id AND msno = :msno"),
            {"id": action_id, "msno": msno},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="해당 알림을 찾을 수 없습니다")
        conn.execute(
            text("UPDATE customer_actions SET is_read = 1 WHERE id = :id"),
            {"id": action_id},
        )
        updated = conn.execute(
            text(
                "SELECT id, msno, action_type, is_read, benefit_key, sent_by, sent_at "
                "FROM customer_actions WHERE id = :id"
            ),
            {"id": action_id},
        ).mappings().first()
    return dict(updated)


@router.post("/actions/read-all")
def mark_all_actions_read(payload: dict = Depends(require_customer)):
    msno = payload["sub"]
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE customer_actions SET is_read = 1 WHERE msno = :msno AND is_read = 0"),
            {"msno": msno},
        )
    return {"status": "ok", "updated": result.rowcount}


@router.post("/benefits/claim", response_model=ActionRecord)
def claim_benefit(body: BenefitClaimRequest, payload: dict = Depends(require_customer)):
    """콘서트 티켓 추첨 응모 / 연차 혜택 / 갱신 즉시 리워드 — 고객이 앱에서 직접 눌러서 받는 혜택.
    같은 benefit_key를 중복 수령하지 못하도록 이미 있으면 그 기록을 그대로 반환한다."""
    msno = payload["sub"]
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id, msno, action_type, is_read, benefit_key, sent_by, sent_at "
                "FROM customer_actions WHERE msno = :msno AND benefit_key = :benefit_key "
                "ORDER BY sent_at DESC LIMIT 1"
            ),
            {"msno": msno, "benefit_key": body.benefit_key},
        ).mappings().first()
        if existing:
            return dict(existing)

        label = BENEFIT_LABELS.get(body.benefit_key, body.benefit_key)
        result = conn.execute(
            text(
                "INSERT INTO customer_actions (msno, action_type, is_read, benefit_key, sent_by) "
                "VALUES (:msno, 'discount_offer', 1, :benefit_key, :sent_by)"
            ),
            {"msno": msno, "benefit_key": body.benefit_key, "sent_by": f"self:{label}"},
        )
        new_id = result.lastrowid
        created = conn.execute(
            text(
                "SELECT id, msno, action_type, is_read, benefit_key, sent_by, sent_at "
                "FROM customer_actions WHERE id = :id"
            ),
            {"id": new_id},
        ).mappings().first()
    return dict(created)
