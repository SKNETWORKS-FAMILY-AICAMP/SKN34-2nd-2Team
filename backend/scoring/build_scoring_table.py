"""
Phase 1 — 전체 고객 스코어링 테이블 생성 (v2 모델 버전)

기존 lightgbm_final.txt(구 모델, model_table_final.csv 기반) 대신, 실제 서빙 성능이
검증된(test_auc=0.9036) lightgbm_enhanced_v2.txt + model_table_enhanced_v2.csv 조합으로
전체 인구를 다시 스코어링한다.

피처는 lightgbm_enhanced_v2_meta.json의 feature_cols(57개)를 그대로 사용해서,
학습 때와 정확히 동일한 피처 집합/순서를 보장한다 (컬럼이 하나라도 빠지면 조용히
틀린 예측을 내는 대신 바로 에러를 낸다).

driver_feature(개별 고객별 이탈 이유)는 넣지 않는다 — 관리자 페이지는 고객 개별 상세가
아니라 "코호트/세그먼트별 리스트"만 필요하다고 확인했고, 그건 이미
export_reference_tables.py가 만드는 segment_drivers 테이블(집계, 몇 % 등)로 충분하다.

실행: python backend/scoring/build_scoring_table.py
"""
import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent  # backend/scoring/ -> 프로젝트 루트
PROCESSED_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

V2_META = json.loads((MODELS_DIR / "lightgbm_enhanced_v2_meta.json").read_text(encoding="utf-8"))
RISK_THRESHOLD = V2_META["threshold"]
FEATURE_COLS = V2_META["feature_cols"]


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


CHUNK_SIZE = 100_000  # 590MB 테이블을 한 번에 다 읽으면 메모리 부족(ArrowMemoryError)이 나서 나눠서 처리


def main():
    step(f"1) v2 모델 로드 + 컬럼 확인 ({V2_META['source_table']})")
    booster = lgb.Booster(model_file=str(MODELS_DIR / "lightgbm_enhanced_v2.txt"))
    src_path = PROCESSED_DIR / V2_META["source_table"]

    header_cols = pd.read_csv(src_path, nrows=0).columns.tolist()
    missing = [c for c in FEATURE_COLS if c not in header_cols]
    if missing:
        raise SystemExit(
            f"[에러] {V2_META['source_table']}에 v2 모델이 학습 때 쓴 피처가 없습니다: {missing}\n"
            f"       -> 이 파일이 lightgbm_enhanced_v2_meta.json의 source_table과 다른 버전인지 확인해주세요."
        )
    has_snapshot = "snapshot" in header_cols
    usecols = ["msno"] + (["snapshot"] if has_snapshot else []) + FEATURE_COLS
    step(f"   -> 필요한 {len(usecols)}개 컬럼만 읽습니다 (전체 {len(header_cols)}개 중)")

    step("2) 이탈확률 예측 (전체 인구, v2 모델) — 10만행씩 청크로 나눠서 메모리 절약")
    keep_cols = ["msno", "days_to_expire", "days_since_last_txn", "churn_proba"]
    if has_snapshot:
        keep_cols.append("snapshot")
    parts = []
    n_rows = 0
    for i, chunk in enumerate(pd.read_csv(src_path, usecols=usecols, chunksize=CHUNK_SIZE)):
        chunk["city"] = chunk["city"].astype("int64").astype("category")
        chunk["registered_via"] = chunk["registered_via"].astype("int64").astype("category")
        chunk["gender"] = chunk["gender"].astype("category")
        chunk["churn_proba"] = booster.predict(chunk[FEATURE_COLS])
        parts.append(chunk[keep_cols].copy())
        n_rows += len(chunk)
        step(f"   -> 청크 {i + 1} 처리 완료 (누적 {n_rows:,}행)")
    df = pd.concat(parts, ignore_index=True)
    del parts

    step("3) msno별 최신 스냅샷 1건만 남기기 (snapshot 컬럼 있으면 그 기준, 없으면 그냥 dedupe)")
    if has_snapshot:
        df = df.sort_values(["msno", "snapshot"]).drop_duplicates("msno", keep="last").reset_index(drop=True)
    else:
        df = df.drop_duplicates("msno", keep="last").reset_index(drop=True)
    step(f"   -> {len(df):,}명 (msno 유니크)")

    step("4) LTV 계산 (prepare_data.py 7단계와 동일 로직)")
    txn = pd.read_csv(
        PROCESSED_DIR / "features_transactions.csv",
        usecols=["msno", "total_amount_paid", "txn_count", "last_payment_plan_days"],
    )
    txn["avg_revenue_per_txn"] = txn["total_amount_paid"] / txn["txn_count"].clip(lower=1)
    plan_days_for_norm = txn["last_payment_plan_days"].clip(lower=7)
    txn["avg_monthly_revenue"] = txn["avg_revenue_per_txn"] / (plan_days_for_norm / 30)

    result = df.merge(txn[["msno", "avg_monthly_revenue"]], on="msno", how="inner")
    result["churn_proba_floored"] = result["churn_proba"].clip(lower=0.01)
    result["expected_lifetime_months"] = (1 / result["churn_proba_floored"]).clip(upper=60)
    result["ltv_approx"] = result["avg_monthly_revenue"] * result["expected_lifetime_months"]

    step("5) 위험군 / 가치군 세그먼트 (threshold는 v2 meta의 검증된 값 사용)")
    ltv_median = result["avg_monthly_revenue"].median()
    result["risk_tier"] = np.where(result["churn_proba"] >= RISK_THRESHOLD, "고위험", "저위험")
    result["ltv_tier"] = np.where(result["avg_monthly_revenue"] >= ltv_median, "고가치", "저가치")
    result["segment"] = result["risk_tier"] + "/" + result["ltv_tier"]
    step(f"   -> 고위험 {int((result['risk_tier']=='고위험').sum()):,}명 / "
         f"저위험 {int((result['risk_tier']=='저위험').sum()):,}명 (threshold={RISK_THRESHOLD:.4f})")

    step("5b) 구독 생애주기 상태 (lifecycle_status) — days_to_expire 기준 순수 후처리 분류")
    result["lifecycle_status"] = np.select(
        [
            result["days_to_expire"].isna(),
            result["days_to_expire"] > 0,
            result["days_to_expire"].between(-30, 0),
        ],
        ["상태확인필요", "구독활성", "갱신유예기간"],
        default="장기만료",
    )
    step("   -> " + ", ".join(
        f"{k} {v:,}명" for k, v in result["lifecycle_status"].value_counts().items()
    ))

    step("6) 최종 컬럼 정리 (schema.sql의 customer_churn_scores와 1:1로 맞춤)")
    final_cols = [
        "msno", "churn_proba", "risk_tier", "ltv_tier", "segment",
        "avg_monthly_revenue", "expected_lifetime_months", "ltv_approx",
        "days_to_expire", "days_since_last_txn", "lifecycle_status",
    ]
    final = result[final_cols].copy()
    final["scored_at"] = pd.Timestamp.now().strftime("%Y-%m-%d")

    out_path = OUT_DIR / "customer_churn_scores.csv"
    final.to_csv(out_path, index=False)
    step(f"완료: {out_path} ({len(final):,} rows, {out_path.stat().st_size / 1e6:.1f} MB)")
    print(final["segment"].value_counts())


if __name__ == "__main__":
    main()
