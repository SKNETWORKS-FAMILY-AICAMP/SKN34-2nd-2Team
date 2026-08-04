"""운영자 전용 API — 분석, 고객 탐색, 개별 액션 및 고객군 캠페인 실행."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.auth import require_staff
from db import get_engine
from app.schemas import (
    ActionRequest,
    ActionsSummaryResponse,
    CampaignCreateRequest,
    CampaignPreviewRequest,
    CampaignPreviewResponse,
    CampaignResponse,
    CustomerListResponse,
    KpiResponse,
)

router = APIRouter()

VALID_ACTION_TYPES = {"reminder", "discount_offer"}
VALID_PURPOSES = {
    "retention": "구독활성",
    "renewal": "갱신유예기간",
    "winback": "장기만료",
}
VALID_RISK_TIERS = {"고위험", "저위험"}
VALID_SEGMENTS = {
    "고위험/고가치",
    "고위험/저가치",
    "저위험/고가치",
    "저위험/저가치",
}
VALID_SELECTION_MODES = {"all_matching", "top_n", "manual"}
MAX_CAMPAIGN_RECIPIENTS = 50000

# ORDER BY 절에 그대로 꽂을 컬럼이라, SQL 인젝션 방지를 위해 화이트리스트로만 허용.
SORTABLE_COLUMNS = {"churn_proba", "ltv_approx"}

# lifecycle_status 화이트리스트 — days_to_expire 기준 구독 생애주기 상태.
# 활성 Retention 대상 / 긴급 갱신 대상 / Win-back 대상이 서로 섞이지 않도록 필터링할 때 쓴다.
VALID_LIFECYCLE_STATUSES = {"구독활성", "갱신유예기간", "장기만료", "상태확인필요"}


def _validate_campaign_filters(
    *,
    purpose: str,
    action_type: str,
    risk_tier: Optional[str],
    segment: Optional[str],
    selection_mode: str,
    audience_limit: Optional[int],
    manual_msnos: Optional[list[str]] = None,
):
    if purpose not in VALID_PURPOSES:
        raise HTTPException(status_code=400, detail="지원하지 않는 캠페인 목적입니다")
    if action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail="지원하지 않는 액션 유형입니다")
    if risk_tier and risk_tier not in VALID_RISK_TIERS:
        raise HTTPException(status_code=400, detail="지원하지 않는 위험도입니다")
    if segment and segment not in VALID_SEGMENTS:
        raise HTTPException(status_code=400, detail="지원하지 않는 세그먼트입니다")
    if selection_mode not in VALID_SELECTION_MODES:
        raise HTTPException(status_code=400, detail="지원하지 않는 대상 선택 방식입니다")
    if selection_mode == "top_n" and not audience_limit:
        raise HTTPException(status_code=400, detail="상위 N명 선택에서는 대상 인원이 필요합니다")
    if selection_mode == "manual" and not manual_msnos:
        raise HTTPException(status_code=400, detail="직접 선택 방식에서는 고객을 1명 이상 추가해야 합니다")
    if manual_msnos and len(manual_msnos) > 500:
        raise HTTPException(status_code=400, detail="직접 선택 고객은 캠페인당 최대 500명입니다")


def _audience_sql_parts(
    *,
    purpose: str,
    action_type: str,
    risk_tier: Optional[str],
    segment: Optional[str],
    exclude_recent_days: int,
    selection_mode: str = "all_matching",
    manual_msnos: Optional[list[str]] = None,
):
    conditions = ["ccs.lifecycle_status = :lifecycle_status"]
    params = {
        "lifecycle_status": VALID_PURPOSES[purpose],
        "action_type": action_type,
        "exclude_recent_days": exclude_recent_days,
    }
    if selection_mode == "manual":
        for index, msno in enumerate(manual_msnos or []):
            params[f"manual_msno_{index}"] = msno
        placeholders = ", ".join(f":manual_msno_{index}" for index in range(len(manual_msnos or [])))
        conditions.append(f"ccs.msno IN ({placeholders})")
    if risk_tier:
        conditions.append("ccs.risk_tier = :risk_tier")
        params["risk_tier"] = risk_tier
    if segment:
        conditions.append("ccs.segment = :segment")
        params["segment"] = segment

    base_where = " AND ".join(conditions)
    recent_exists = (
        "EXISTS ("
        "SELECT 1 FROM customer_actions ca "
        "WHERE ca.msno = ccs.msno "
        "AND ca.action_type = :action_type "
        "AND ca.sent_at >= TIMESTAMPADD(DAY, -:exclude_recent_days, NOW())"
        ")"
        if exclude_recent_days > 0
        else "FALSE"
    )
    eligible_where = f"{base_where} AND NOT ({recent_exists})"
    return base_where, eligible_where, params


def _preview_campaign(
    conn,
    *,
    purpose: str,
    action_type: str,
    risk_tier: Optional[str],
    segment: Optional[str],
    selection_mode: str,
    audience_limit: Optional[int],
    exclude_recent_days: int,
    sort_by: str,
    manual_msnos: Optional[list[str]] = None,
):
    base_where, eligible_where, params = _audience_sql_parts(
        purpose=purpose,
        action_type=action_type,
        risk_tier=risk_tier,
        segment=segment,
        exclude_recent_days=exclude_recent_days,
        selection_mode=selection_mode,
        manual_msnos=manual_msnos,
    )
    requested_count = len(manual_msnos or []) if selection_mode == "manual" else None
    matched_count = conn.execute(
        text(f"SELECT COUNT(*) FROM customer_churn_scores ccs WHERE {base_where}"),
        params,
    ).scalar() or 0
    eligible_count = conn.execute(
        text(f"SELECT COUNT(*) FROM customer_churn_scores ccs WHERE {eligible_where}"),
        params,
    ).scalar() or 0
    excluded_count = matched_count - eligible_count
    sort_col = sort_by if sort_by in SORTABLE_COLUMNS else "churn_proba"
    sample = conn.execute(
        text(
            f"SELECT ccs.* FROM customer_churn_scores ccs "
            f"WHERE {eligible_where} ORDER BY ccs.{sort_col} DESC LIMIT 10"
        ),
        params,
    ).mappings().all()

    selected_count = (
        min(eligible_count, audience_limit or 0)
        if selection_mode == "top_n"
        else eligible_count
    )
    excluded_condition_count = (
        max((requested_count or 0) - matched_count, 0)
        if selection_mode == "manual"
        else 0
    )
    launchable = selected_count > 0 and selected_count <= MAX_CAMPAIGN_RECIPIENTS
    warning = None
    if selected_count == 0:
        warning = "조건에 맞는 발송 대상이 없습니다."
    elif selected_count > MAX_CAMPAIGN_RECIPIENTS:
        warning = (
            f"데모 환경에서는 한 캠페인당 최대 {MAX_CAMPAIGN_RECIPIENTS:,}명까지 실행할 수 있습니다. "
            "조건을 좁히거나 상위 N명 방식을 선택하세요."
        )

    return {
        "requested_count": int(requested_count if requested_count is not None else matched_count),
        "matched_count": int(matched_count),
        "excluded_condition_count": int(excluded_condition_count),
        "excluded_recent_count": int(excluded_count),
        "eligible_count": int(eligible_count),
        "selected_count": int(selected_count),
        "launchable": launchable,
        "warning": warning,
        "sample": [dict(row) for row in sample],
        "eligible_where": eligible_where,
        "params": params,
        "sort_col": sort_col,
    }


def _campaign_response(row) -> dict:
    return dict(row)


@router.get("/customers", response_model=CustomerListResponse)
def list_customers(
    risk_tier: Optional[str] = Query(None, description="고위험 | 저위험"),
    segment: Optional[str] = Query(None, description="예: 고위험/고가치"),
    lifecycle_status: Optional[str] = Query(
        None, description="구독활성(Retention) | 갱신유예기간(긴급갱신) | 장기만료(Win-back) | 상태확인필요"
    ),
    sort_by: str = Query("churn_proba", description="churn_proba | ltv_approx"),
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
    if lifecycle_status and lifecycle_status in VALID_LIFECYCLE_STATUSES:
        conditions.append("lifecycle_status = :lifecycle_status")
        params["lifecycle_status"] = lifecycle_status
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sort_col = sort_by if sort_by in SORTABLE_COLUMNS else "churn_proba"

    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM customer_churn_scores {where}"), params).scalar()
        rows = conn.execute(
            text(
                f"SELECT * FROM customer_churn_scores {where} "
                f"ORDER BY {sort_col} DESC LIMIT :limit OFFSET :offset"
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


@router.get("/overview")
def overview(_: dict = Depends(require_staff)):
    """관리자 운영 홈에 필요한 실제 DB 집계를 한 번의 화면 요청으로 반환한다."""
    engine = get_engine()
    with engine.connect() as conn:
        summary = conn.execute(
            text(
                "SELECT COUNT(*) AS total_customers, "
                "SUM(risk_tier = '고위험') AS high_risk_total, "
                "SUM(lifecycle_status = '구독활성' AND risk_tier = '고위험') AS retention_high_risk, "
                "SUM(lifecycle_status = '갱신유예기간' AND risk_tier = '고위험') AS renewal_high_risk, "
                "SUM(lifecycle_status = '장기만료') AS winback_total, "
                "SUM(lifecycle_status = '장기만료' AND risk_tier = '고위험') AS winback_high_risk, "
                "SUM(lifecycle_status = '구독활성' AND segment = '고위험/고가치') AS retention_priority "
                "FROM customer_churn_scores"
            )
        ).mappings().one()
        segment_counts = conn.execute(
            text(
                "SELECT segment, COUNT(*) AS cnt FROM customer_churn_scores "
                "GROUP BY segment ORDER BY cnt DESC"
            )
        ).mappings().all()
        lifecycle_counts = conn.execute(
            text(
                "SELECT lifecycle_status, risk_tier, COUNT(*) AS cnt "
                "FROM customer_churn_scores GROUP BY lifecycle_status, risk_tier "
                "ORDER BY lifecycle_status, risk_tier"
            )
        ).mappings().all()
        activity = conn.execute(
            text(
                "SELECT "
                "(SELECT COUNT(*) FROM customer_actions) AS action_total, "
                "(SELECT COUNT(DISTINCT msno) FROM customer_actions) AS action_customers, "
                "(SELECT COUNT(*) FROM campaigns) AS campaign_total"
            )
        ).mappings().one()

    return {
        "summary": {key: int(value or 0) for key, value in dict(summary).items()},
        "segment_counts": [dict(row) for row in segment_counts],
        "lifecycle_counts": [dict(row) for row in lifecycle_counts],
        "activity": {key: int(value or 0) for key, value in dict(activity).items()},
    }


@router.get("/campaigns/preview", response_model=CampaignPreviewResponse)
def preview_campaign(
    purpose: str = Query(..., description="retention | renewal | winback"),
    action_type: str = Query(..., description="reminder | discount_offer"),
    risk_tier: Optional[str] = Query(None, description="고위험 | 저위험"),
    segment: Optional[str] = Query(None, description="내부 저장값: 고위험/고가치 등"),
    selection_mode: str = Query("all_matching", description="all_matching | top_n"),
    audience_limit: Optional[int] = Query(None, ge=1, le=MAX_CAMPAIGN_RECIPIENTS),
    exclude_recent_days: int = Query(7, ge=0, le=365),
    sort_by: str = Query("churn_proba", description="churn_proba | ltv_approx"),
    _: dict = Depends(require_staff),
):
    """캠페인을 쓰기 전에 모집단·최근 중복 제외·최종 선택 인원과 샘플을 조회한다."""
    _validate_campaign_filters(
        purpose=purpose,
        action_type=action_type,
        risk_tier=risk_tier,
        segment=segment,
        selection_mode=selection_mode,
        audience_limit=audience_limit,
    )
    engine = get_engine()
    with engine.connect() as conn:
        result = _preview_campaign(
            conn,
            purpose=purpose,
            action_type=action_type,
            risk_tier=risk_tier,
            segment=segment,
            selection_mode=selection_mode,
            audience_limit=audience_limit,
            exclude_recent_days=exclude_recent_days,
            sort_by=sort_by,
        )
    return {key: value for key, value in result.items() if key not in {"eligible_where", "params", "sort_col"}}


@router.post("/campaigns/preview", response_model=CampaignPreviewResponse)
def preview_campaign_selection(
    body: CampaignPreviewRequest,
    _: dict = Depends(require_staff),
):
    """직접 선택 고객을 포함해 캠페인 대상과 제외 결과를 실행 전에 검증한다."""
    _validate_campaign_filters(
        purpose=body.purpose,
        action_type=body.action_type,
        risk_tier=body.risk_tier,
        segment=body.segment,
        selection_mode=body.selection_mode,
        audience_limit=body.audience_limit,
        manual_msnos=body.manual_msnos,
    )
    engine = get_engine()
    with engine.connect() as conn:
        result = _preview_campaign(
            conn,
            purpose=body.purpose,
            action_type=body.action_type,
            risk_tier=body.risk_tier,
            segment=body.segment,
            selection_mode=body.selection_mode,
            audience_limit=body.audience_limit,
            exclude_recent_days=body.exclude_recent_days,
            sort_by="churn_proba",
            manual_msnos=body.manual_msnos,
        )
    return {key: value for key, value in result.items() if key not in {"eligible_where", "params", "sort_col"}}


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    limit: int = Query(20, ge=1, le=100),
    _: dict = Depends(require_staff),
):
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM campaigns ORDER BY created_at DESC, id DESC LIMIT :limit"),
            {"limit": limit},
        ).mappings().all()
    return [_campaign_response(row) for row in rows]


@router.post("/campaigns", response_model=CampaignResponse)
def create_campaign(body: CampaignCreateRequest, staff: dict = Depends(require_staff)):
    """필터에 맞는 고객군을 스냅샷으로 고정하고 데모 알림 발송 기록을 일괄 생성한다.

    외부 이메일/푸시는 발송하지 않는다. 동일 request_key 재요청은 기존 캠페인을 반환한다.
    """
    _validate_campaign_filters(
        purpose=body.purpose,
        action_type=body.action_type,
        risk_tier=body.risk_tier,
        segment=body.segment,
        selection_mode=body.selection_mode,
        audience_limit=body.audience_limit,
        manual_msnos=body.manual_msnos,
    )
    engine = get_engine()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT * FROM campaigns WHERE request_key = :request_key"),
            {"request_key": body.request_key},
        ).mappings().first()
        if existing:
            return _campaign_response(existing)

        preview = _preview_campaign(
            conn,
            purpose=body.purpose,
            action_type=body.action_type,
            risk_tier=body.risk_tier,
            segment=body.segment,
            selection_mode=body.selection_mode,
            audience_limit=body.audience_limit,
            exclude_recent_days=body.exclude_recent_days,
            sort_by="churn_proba",
            manual_msnos=body.manual_msnos,
        )
        if not preview["launchable"]:
            raise HTTPException(status_code=400, detail=preview["warning"] or "캠페인을 실행할 수 없습니다")

        insert_result = conn.execute(
            text(
                "INSERT INTO campaigns ("
                "request_key, name, purpose, action_type, lifecycle_status, risk_tier, segment, "
                "selection_mode, audience_limit, exclude_recent_days, matched_count, excluded_count, "
                "recipient_count, status, created_by"
                ") VALUES ("
                ":request_key, :name, :purpose, :action_type, :lifecycle_status, :risk_tier, :segment, "
                ":selection_mode, :audience_limit, :exclude_recent_days, :matched_count, :excluded_count, "
                "0, 'processing', :created_by"
                ")"
            ),
            {
                "request_key": body.request_key,
                "name": body.name.strip(),
                "purpose": body.purpose,
                "action_type": body.action_type,
                "lifecycle_status": VALID_PURPOSES[body.purpose],
                "risk_tier": body.risk_tier,
                "segment": body.segment,
                "selection_mode": body.selection_mode,
                "audience_limit": len(body.manual_msnos) if body.selection_mode == "manual" else body.audience_limit,
                "exclude_recent_days": body.exclude_recent_days,
                "matched_count": preview["matched_count"],
                "excluded_count": preview["excluded_condition_count"] + preview["excluded_recent_count"],
                "created_by": staff.get("sub"),
            },
        )
        campaign_id = insert_result.lastrowid
        recipient_params = {
            **preview["params"],
            "campaign_id": campaign_id,
            "recipient_limit": preview["selected_count"],
        }
        recipient_result = conn.execute(
            text(
                "INSERT INTO campaign_recipients "
                "(campaign_id, msno, group_type, delivery_status, sent_at) "
                "SELECT :campaign_id, ccs.msno, 'treatment', 'recorded', NOW() "
                "FROM customer_churn_scores ccs "
                f"WHERE {preview['eligible_where']} "
                f"ORDER BY ccs.{preview['sort_col']} DESC LIMIT :recipient_limit"
            ),
            recipient_params,
        )
        recipient_count = max(recipient_result.rowcount or 0, 0)
        conn.execute(
            text(
                "INSERT INTO customer_actions (msno, campaign_id, action_type, sent_by, sent_at) "
                "SELECT cr.msno, :campaign_id, :action_type, :sent_by, cr.sent_at "
                "FROM campaign_recipients cr WHERE cr.campaign_id = :campaign_id"
            ),
            {
                "campaign_id": campaign_id,
                "action_type": body.action_type,
                "sent_by": staff.get("sub"),
            },
        )
        conn.execute(
            text(
                "UPDATE campaigns SET recipient_count = :recipient_count, "
                "status = 'completed', launched_at = NOW() WHERE id = :campaign_id"
            ),
            {"recipient_count": recipient_count, "campaign_id": campaign_id},
        )
        created = conn.execute(
            text("SELECT * FROM campaigns WHERE id = :campaign_id"),
            {"campaign_id": campaign_id},
        ).mappings().one()
    return _campaign_response(created)


@router.get("/actions/summary", response_model=ActionsSummaryResponse)
def actions_summary(_: dict = Depends(require_staff)):
    """지금까지 실제로 발송한 리마인드/할인오퍼 현황(건수/세그먼트별 분포/최근 발송 내역).
    "전환됐는지"는 추적할 시계열 데이터가 없어서(customer_churn_scores가 특정 시점 스냅샷이라)
    여기서는 "실제로 몇 건, 누구에게, 언제 보냈는지"만 정직하게 집계한다 — 전환율은 계산하지 않는다."""
    engine = get_engine()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM customer_actions")).scalar()
        by_type = conn.execute(
            text("SELECT action_type, COUNT(*) AS cnt FROM customer_actions GROUP BY action_type")
        ).mappings().all()
        by_segment = conn.execute(
            text(
                "SELECT ccs.segment AS segment, COUNT(*) AS cnt "
                "FROM customer_actions ca JOIN customer_churn_scores ccs ON ca.msno = ccs.msno "
                "GROUP BY ccs.segment ORDER BY cnt DESC"
            )
        ).mappings().all()
        recent = conn.execute(
            text(
                "SELECT ca.msno, ca.action_type, ca.sent_by, ca.sent_at, ca.campaign_id, "
                "c.name AS campaign_name, ccs.segment "
                "FROM customer_actions ca JOIN customer_churn_scores ccs ON ca.msno = ccs.msno "
                "LEFT JOIN campaigns c ON ca.campaign_id = c.id "
                "ORDER BY ca.sent_at DESC LIMIT 10"
            )
        ).mappings().all()

    return {
        "total": total or 0,
        "by_type": [dict(r) for r in by_type],
        "by_segment": [dict(r) for r in by_segment],
        "recent": [dict(r) for r in recent],
    }


@router.post("/customers/{msno}/actions")
def send_customer_action(msno: str, body: ActionRequest, staff: dict = Depends(require_staff)):
    """[관리자 화면(kkbox_admin.html) 미사용] 관리자가 특정 고객에게 리마인드/할인 오퍼를
    "발송"한 것으로 기록. 실제 이메일/푸시 발송은 하지 않고, DB에 기록만 남긴다 — 그 msno로
    고객 로그인하면 /me/actions에서 이 기록을 조회해 소비자 앱 알림함에 보여준다.

    개별 고객 1명 대상 액션은 현재 화면에서 /admin/campaigns(POST)의
    selection_mode="manual" + manual_msnos=[msno] 경로로 나가고 있어서, 이 엔드포인트는
    화면 어디서도 호출되지 않는다. API 단독 테스트(Swagger)용으로만 남겨둠 — 필요 없으면
    삭제해도 캠페인 플로우에는 영향 없음."""
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
