"""
대시보드용 경량 데이터 준비 스크립트.

노트북(EDA/preprocessing/modeling/analytics)에서 이미 검증한 결과를 재사용하거나,
빠르게 재계산 가능한 것(리텐션/코호트/퍼널/LTV)은 다시 계산해서
streamlit_app/data/ 아래에 작은 파일로 저장한다.
대시보드 자체는 이 폴더의 파일만 읽으므로, 30GB 원본이나 196만행 테이블을
직접 로드하지 않는다 (추후 배포 시에도 이 폴더만 있으면 됨).

실행: python prepare_data.py  (프로젝트 루트가 아니라 streamlit_app/ 안에서 실행)
"""
import json
import pickle
import shutil
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CUTOFF_DATE = pd.Timestamp("2017-02-28")
RISK_THRESHOLD = json.loads((MODELS_DIR / "best_params.json").read_text())["threshold"]


def save_json(name, obj):
    with open(OUT_DIR / name, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"저장: {name}")


def save_csv(name, df):
    df.to_csv(OUT_DIR / name, index=False)
    print(f"저장: {name} ({len(df):,} rows)")


# 1. EDA 요약 (이미 EDA 노트북에서 검증한 값들)
print("=== 1. EDA 요약 ===")
eda_summary = {
    "members_v3": {"rows": 6769473, "gender_missing_pct": 65.43, "bd_invalid_pct": 67.2},
    "transactions": {"rows_raw": 21547746, "rows_dedup": 21544407, "duplicate_rows": 3339, "unique_users": 2363626},
    "user_logs": {"rows": 392106543, "size_gb": 30, "unique_users": 5234111},
    "train": {"rows": 992931, "churn_rate": 0.0639, "cohort_month": "2017-02"},
    "train_v2": {"rows": 970960, "churn_rate": 0.0899, "cohort_month": "2017-03"},
    "cohort_overlap_users": 881701,
    "label_agreement_rate": 0.9478,
    "pooled_labeled_users": 1082190,
    "risk_threshold": RISK_THRESHOLD,
}
save_json("eda_summary.json", eda_summary)


# 2. 모델 비교 (기존 결과 복사)
print("=== 2. 모델 비교 ===")
shutil.copy(MODELS_DIR / "model_comparison.csv", OUT_DIR / "model_comparison.csv")
print("저장: model_comparison.csv")


# 3. LightGBM 피처 중요도
print("=== 3. 피처 중요도 ===")
model = lgb.Booster(model_file=str(MODELS_DIR / "lightgbm_final.txt"))
feature_names = model.feature_name()
importance = pd.DataFrame({
    "feature": feature_names,
    "gain": model.feature_importance(importance_type="gain"),
}).sort_values("gain", ascending=False)
save_csv("feature_importance.csv", importance)


# 4. SHAP (05단계 산출물 재사용, 대시보드용으로 가볍게 저장)
print("=== 4. SHAP ===")
with open(PROCESSED_DIR / "shap_sample.pkl", "rb") as f:
    shap_data = pickle.load(f)

shap_df = pd.DataFrame(shap_data["shap_values"], columns=shap_data["feature_cols"])
shap_df.insert(0, "msno", shap_data["msno"])
shap_df.insert(1, "pred_proba", shap_data["pred_proba"])
shap_df.to_parquet(OUT_DIR / "shap_sample.parquet", index=False)
print(f"저장: shap_sample.parquet ({len(shap_df):,} rows)")

X_sample_df = shap_data["X_sample"].copy()
X_sample_df.insert(0, "msno", shap_data["msno"])
X_sample_df.to_parquet(OUT_DIR / "shap_features.parquet", index=False)
print(f"저장: shap_features.parquet")

mean_abs_shap = pd.DataFrame({
    "feature": shap_data["feature_cols"],
    "mean_abs_shap": np.abs(shap_data["shap_values"]).mean(axis=0),
}).sort_values("mean_abs_shap", ascending=False)
save_csv("shap_importance.csv", mean_abs_shap)


# 5. Retention / Cohort (DuckDB 재계산, analytics/02와 동일 로직)
print("=== 5. Retention/Cohort ===")
con = duckdb.connect()
cohort_raw = con.sql(f"""
    WITH txn_months AS (
        SELECT DISTINCT msno, DATE_TRUNC('month', STRPTIME(CAST(transaction_date AS VARCHAR), '%Y%m%d')) AS txn_month
        FROM read_csv_auto('{RAW_DIR / "transactions.csv"}')
    ),
    cohort AS (SELECT msno, MIN(txn_month) AS cohort_month FROM txn_months GROUP BY msno)
    SELECT c.cohort_month, DATE_DIFF('month', c.cohort_month, t.txn_month) AS month_offset,
           COUNT(DISTINCT t.msno) AS active_users
    FROM txn_months t JOIN cohort c USING (msno)
    WHERE DATE_DIFF('month', c.cohort_month, t.txn_month) BETWEEN 0 AND 11
    GROUP BY c.cohort_month, month_offset
    ORDER BY c.cohort_month, month_offset
""").df()

cohort_sizes = cohort_raw[cohort_raw["month_offset"] == 0].set_index("cohort_month")["active_users"]
pivot = cohort_raw.pivot(index="cohort_month", columns="month_offset", values="active_users")
retention_pct = pivot.div(cohort_sizes, axis=0) * 100
retention_pct = retention_pct[retention_pct.index <= pd.Timestamp("2016-02-01")]
retention_pct.index = retention_pct.index.strftime("%Y-%m")
retention_pct.reset_index().rename(columns={"index": "cohort_month"}).to_csv(OUT_DIR / "retention_cohort.csv", index=False)
print(f"저장: retention_cohort.csv ({len(retention_pct)} cohorts)")


# 5b. 2015-06 코호트 리텐션 급락 조사 (신규 유저의 첫 결제 특성 비교)
print("=== 5b. 2015-06 코호트 조사 ===")
first_txn_by_method = con.sql(f"""
    WITH txn AS (
        SELECT msno, transaction_date, payment_method_id, payment_plan_days, actual_amount_paid,
               DATE_TRUNC('month', STRPTIME(CAST(transaction_date AS VARCHAR), '%Y%m%d')) AS txn_month
        FROM read_csv_auto('{RAW_DIR / "transactions.csv"}')
    ),
    first_txn AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY msno ORDER BY transaction_date ASC, payment_method_id ASC) AS rn
        FROM txn
    ),
    cohort AS (SELECT msno, MIN(txn_month) AS cohort_month FROM txn GROUP BY msno)
    SELECT c.cohort_month, f.payment_method_id, f.payment_plan_days, f.actual_amount_paid
    FROM first_txn f JOIN cohort c ON f.msno = c.msno AND f.rn = 1
    WHERE c.cohort_month BETWEEN '2015-04-01' AND '2015-08-01'
""").df()
first_txn_by_method["cohort_month"] = first_txn_by_method["cohort_month"].dt.strftime("%Y-%m")

cohort_records = []
for month, grp in first_txn_by_method.groupby("cohort_month"):
    method_counts = grp["payment_method_id"].value_counts()
    top_method = method_counts.index[0]
    cohort_records.append({
        "cohort_month": month,
        "new_users": int(len(grp)),
        "top_payment_method": int(top_method),
        "top_payment_method_pct": round(float(method_counts.iloc[0] / len(grp) * 100), 1),
        "top_plan_days": int(grp["payment_plan_days"].mode().iloc[0]),
        "avg_amount_paid": round(float(grp["actual_amount_paid"].mean()), 1),
    })
cohort_records.sort(key=lambda r: r["cohort_month"])

jun2015_investigation = {
    "cohorts": cohort_records,
    "news_reference": {
        "title": "幫 KKBOX 改頭換面！即日起新增多款特色面板 (ETtoday, 2015-06-10)",
        "url": "https://www.ettoday.net/news/20150610/519023.htm",
        "note": "2015년 6월 실제 KKBOX 공지 기사이나, 신규가입 프로모션이 아닌 기존 유료회원 대상 UI/혜택 개편 공지라 이 급증과 직접적 인과관계는 확인되지 않음.",
    },
}
save_json("jun2015_investigation.json", jun2015_investigation)


# 6. Funnel (analytics/03과 동일 로직)
print("=== 6. Funnel ===")
members = pd.read_csv(RAW_DIR / "members_v3.csv", usecols=["msno"])
transactions_feat = pd.read_csv(PROCESSED_DIR / "features_transactions.csv", usecols=["msno", "auto_renew_rate"])
user_logs_feat = pd.read_csv(PROCESSED_DIR / "features_user_logs.csv", usecols=["msno", "full_active_days"])
model_table_labels = pd.read_csv(PROCESSED_DIR / "model_table_final.csv", usecols=["msno", "is_churn"])

all_members = set(members["msno"])
paid_set = set(transactions_feat["msno"])
used_set = set(user_logs_feat["msno"])
repeat_set = set(user_logs_feat.loc[user_logs_feat["full_active_days"] >= 7, "msno"])
auto_renew_set = set(transactions_feat.loc[transactions_feat["auto_renew_rate"] > 0, "msno"])
user_level_churn = model_table_labels.groupby("msno")["is_churn"].max()
labeled_msno = set(user_level_churn.index)
retained_msno = set(user_level_churn[user_level_churn == 0].index)

stage1 = all_members
stage2 = stage1 & paid_set
stage3 = stage2 & used_set
stage4 = stage3 & repeat_set
stage5 = stage4 & auto_renew_set
stage6_denominator = stage5 & labeled_msno
stage6 = stage6_denominator & retained_msno

funnel = pd.DataFrame({
    "stage": ["1. 가입", "2. 첫 결제", "3. 이용", "4. 반복 이용", "5. 자동 갱신", "6. 재구독(라벨 코호트 한정)"],
    "count": [len(stage1), len(stage2), len(stage3), len(stage4), len(stage5), len(stage6)],
    "denominator": [None, len(stage1), len(stage2), len(stage3), len(stage4), len(stage6_denominator)],
})
funnel["stage_conversion_pct"] = (funnel["count"] / funnel["denominator"] * 100).round(1)
funnel["overall_pct"] = (funnel["count"] / len(stage1) * 100).round(1)
save_csv("funnel.csv", funnel)


# 7. LTV + Retention Priority (analytics/04와 동일 로직, 전체 라벨 인구로 계산 후 대시보드용 샘플만 저장)
print("=== 7. LTV ===")
df = pd.read_csv(PROCESSED_DIR / "model_table_final.csv")
df["city"] = df["city"].astype("int64").astype("category")
df["registered_via"] = df["registered_via"].astype("int64").astype("category")
df["gender"] = df["gender"].astype("category")
DROP_COLS = ["msno", "snapshot", "split", "is_churn"]
FEATURE_COLS = [c for c in df.columns if c not in DROP_COLS]
df["churn_proba"] = model.predict(df[FEATURE_COLS])
user_churn_proba = df.groupby("msno")["churn_proba"].mean().rename("churn_proba")

txn = pd.read_csv(PROCESSED_DIR / "features_transactions.csv", usecols=["msno", "total_amount_paid", "txn_count"])
txn["avg_monthly_revenue"] = txn["total_amount_paid"] / txn["txn_count"].clip(lower=1)
ltv_df = txn.merge(user_churn_proba, on="msno", how="inner")
ltv_df["churn_proba_floored"] = ltv_df["churn_proba"].clip(lower=0.01)
ltv_df["expected_lifetime_months"] = (1 / ltv_df["churn_proba_floored"]).clip(upper=60)
ltv_df["ltv_approx"] = ltv_df["avg_monthly_revenue"] * ltv_df["expected_lifetime_months"]

ltv_median = ltv_df["avg_monthly_revenue"].median()
def quadrant(row):
    risk = "고위험" if row["churn_proba"] >= RISK_THRESHOLD else "저위험"
    value = "고가치" if row["avg_monthly_revenue"] >= ltv_median else "저가치"
    return f"{risk}/{value}"
ltv_df["segment"] = ltv_df.apply(quadrant, axis=1)

save_json("ltv_summary.json", {
    "value_median": float(ltv_median),
    "risk_threshold": RISK_THRESHOLD,
    "segment_counts": ltv_df["segment"].value_counts().to_dict(),
})
sample_for_dash = ltv_df.sample(n=min(30_000, len(ltv_df)), random_state=42)
save_csv("ltv_sample.csv", sample_for_dash)

top_priority = (
    ltv_df[ltv_df["segment"] == "고위험/고가치"]
    .sort_values("ltv_approx", ascending=False)
    .head(20)[["msno", "churn_proba", "avg_monthly_revenue", "expected_lifetime_months", "ltv_approx"]]
)
save_csv("ltv_top_priority.csv", top_priority)


# 8. 세부 세그멘테이션 (analytics/06과 동일 로직, SHAP 샘플 재사용)
print("=== 8. Segmentation ===")
CATEGORY_MAP = {
    "결제/구독 상태": [
        "last_plan_list_price", "last_is_auto_renew", "last_actual_amount_paid", "last_payment_plan_days",
        "auto_renew_rate", "cancel_rate", "cancel_count", "avg_discount", "days_to_expire",
        "total_amount_paid", "payment_method_nunique", "plan_days_nunique", "txn_count",
        "days_since_last_txn", "has_transaction_record",
    ],
    "청취 활동 감소": [
        "d7_active_days", "d30_active_days", "d90_active_days", "full_active_days",
        "d7_avg_num_unq", "d30_avg_num_unq", "d90_avg_num_unq", "full_avg_num_unq",
        "d7_avg_total_secs", "d30_avg_total_secs", "d90_avg_total_secs", "full_avg_total_secs",
        "d7_completion_rate", "d30_completion_rate", "d90_completion_rate", "full_completion_rate",
        "trend_secs_recent15_vs_prior15", "has_log_activity",
    ],
    "고객 프로필": ["city", "registered_via", "gender", "bd_clean", "bd_is_missing", "tenure_days", "has_member_record"],
}
feature_cols = shap_data["feature_cols"]
shap_values = shap_data["shap_values"]
pred_proba = shap_data["pred_proba"]
msno_arr = shap_data["msno"]

shap_df_raw = pd.DataFrame(shap_values, columns=feature_cols)
high_risk_mask = pred_proba >= RISK_THRESHOLD
high_risk_shap = shap_df_raw.loc[high_risk_mask]
detail_driver = high_risk_shap.idxmax(axis=1)

action_map = {
    "days_since_last_txn": "장기 미결제 고객 리마인드 발송",
    "days_to_expire": "만료 임박 고객 대상 갱신 안내/프로모션",
    "last_is_auto_renew": "자동갱신 미설정 고객에게 자동갱신 전환 유도",
    "auto_renew_rate": "자동갱신 이력이 낮은 고객에게 자동갱신 혜택 안내",
    "cancel_rate": "과거 취소 이력이 있는 고객 대상 이탈 사유 설문/맞춤 오퍼",
    "last_plan_list_price": "요금제 부담 완화(다운그레이드/할인) 옵션 안내",
    "last_actual_amount_paid": "요금제 부담 완화(다운그레이드/할인) 옵션 안내",
    "total_amount_paid": "장기/고액 결제 고객 대상 VIP 리텐션 케어",
    "d7_active_days": "최근 7일 청취 급감 고객에게 개인화 추천 알림",
    "d30_active_days": "최근 30일 청취 감소 고객에게 개인화 추천 알림",
    "d90_active_days": "중기 청취 감소 고객에게 콘텐츠 추천 리마인드",
    "full_active_days": "저활동 고객 대상 온보딩/사용법 안내 강화",
    "trend_secs_recent15_vs_prior15": "청취량 급감 추세 고객에게 즉시 개인화 추천 발송",
    "tenure_days": "신규 가입자 대상 온보딩 강화",
}
segment_table = detail_driver.value_counts().rename("count").to_frame()
segment_table["pct"] = (segment_table["count"] / high_risk_mask.sum() * 100).round(1)
segment_table["suggested_action"] = segment_table.index.map(lambda f: action_map.get(f, "개별 분석 필요"))
segment_table = segment_table.reset_index().rename(columns={"index": "driver_feature"})
save_csv("segmentation.csv", segment_table)
save_json("segmentation_meta.json", {"high_risk_n": int(high_risk_mask.sum()), "sample_n": len(pred_proba)})

print("\n모든 대시보드 데이터 준비 완료 ->", OUT_DIR)
