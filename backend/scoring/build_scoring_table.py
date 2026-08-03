"""
Phase 1 — 전체 고객 스코어링 테이블 생성 (kkbox-pipeline-plan 문서 Phase 1)

streamlit_app/prepare_data.py의 7단계(LTV) 로직을 재사용해 "서비스용 전체 인구"
(~99만 msno)의 이탈확률/세그먼트/LTV를 계산한다.

* driver_feature(개별 고객별 이탈 이유)는 넣지 않는다. 관리자 페이지는 고객 개별 상세가
  아니라 "코호트/세그먼트별 리스트"만 필요하다고 확인했고, 그건 이미
  export_reference_tables.py가 만드는 segment_drivers 테이블(집계, 몇 % 등)로 충분하다.
  -> 그래서 제일 느렸던 SHAP(pred_contrib) 단계를 아예 뺐다. predict()만 쓰므로
     99만 행이어도 몇 분 안에 끝날 것이다.

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

RISK_THRESHOLD = json.loads((MODELS_DIR / "lightgbm_enhanced_v2_meta.json").read_text())["threshold"]
DROP_COLS = ["msno", "snapshot", "split", "is_churn"]


def step(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    step("1) 모델 + 전체 피처 테이블 로드")
    booster = lgb.Booster(model_file=str(MODELS_DIR / "lightgbm_enhanced_v2.txt"))
    df = pd.read_csv(PROCESSED_DIR / "model_table_enhanced_v2.csv")
    df["city"] = df["city"].astype("int64").astype("category")
    df["registered_via"] = df["registered_via"].astype("int64").astype("category")
    df["gender"] = df["gender"].astype("category")

    step("2) msno별 최신 스냅샷 1건만 남기기 (실제로는 이미 1:1이라 거의 즉시 끝남)")
    df = df.sort_values(["msno", "snapshot"]).drop_duplicates("msno", keep="last").reset_index(drop=True)
    step(f"   -> {len(df):,}명 (msno 유니크)")

    FEATURE_COLS = [c for c in df.columns if c not in DROP_COLS]

    step("3) 이탈확률 예측 (전체 인구)")
    df["churn_proba"] = booster.predict(df[FEATURE_COLS])

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

    step("5) 위험군 / 가치군 세그먼트")
    ltv_median = result["avg_monthly_revenue"].median()
    result["risk_tier"] = np.where(result["churn_proba"] >= RISK_THRESHOLD, "고위험", "저위험")
    result["ltv_tier"] = np.where(result["avg_monthly_revenue"] >= ltv_median, "고가치", "저가치")
    result["segment"] = result["risk_tier"] + "/" + result["ltv_tier"]
    step(f"   -> 고위험 {int((result['risk_tier']=='고위험').sum()):,}명 / "
         f"저위험 {int((result['risk_tier']=='저위험').sum()):,}명")

    step("6) 최종 컬럼 정리 (schema.sql의 customer_churn_scores와 1:1로 맞춤)")
    final_cols = [
        "msno", "churn_proba", "risk_tier", "ltv_tier", "segment",
        "avg_monthly_revenue", "expected_lifetime_months", "ltv_approx",
        "days_to_expire", "days_since_last_txn",
    ]
    final = result[final_cols].copy()
    final["scored_at"] = pd.Timestamp.now().strftime("%Y-%m-%d")

    out_path = OUT_DIR / "customer_churn_scores.csv"
    final.to_csv(out_path, index=False)
    step(f"완료: {out_path} ({len(final):,} rows, {out_path.stat().st_size / 1e6:.1f} MB)")
    print(final["segment"].value_counts())


if __name__ == "__main__":
    main()
