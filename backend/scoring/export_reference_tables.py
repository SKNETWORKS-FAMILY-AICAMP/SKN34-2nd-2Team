"""MySQL 서빙 DB용 참조 테이블 5개를 직접 생성한다.

별도 대시보드 중간 산출물에 의존하지 않고, 검증된 모델·전처리 산출물과 원본 CSV에서
관리자 분석 화면에 필요한 경량 CSV를 만든다.

실행: python backend/scoring/export_reference_tables.py
"""

import json
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CUTOFF_DATE = pd.Timestamp("2017-01-31")

DRIVER_KO = {
    "days_to_expire": "만료 임박",
    "days_since_last_txn": "장기 미결제",
    "last_is_auto_renew": "자동갱신 해제",
    "cancel_rate": "취소 이력",
    "auto_renew_rate": "자동갱신 낮음",
    "last_actual_amount_paid": "결제액 하락",
}

ACTION_MAP = {
    "days_since_last_txn": "장기 미결제 고객 리마인드 발송",
    "days_to_expire": "만료 임박 고객 대상 갱신 안내/프로모션",
    "last_is_auto_renew": "자동갱신 미설정 고객에게 자동갱신 전환 유도",
    "auto_renew_rate": "자동갱신 이력이 낮은 고객에게 자동갱신 혜택 안내",
    "cancel_rate": "과거 취소 이력이 있는 고객 대상 이탈 사유 설문/맞춤 오퍼",
    "last_plan_list_price": "요금제 부담 완화 옵션 안내",
    "last_actual_amount_paid": "요금제 부담 완화 옵션 안내",
    "total_amount_paid": "장기/고액 결제 고객 대상 VIP 리텐션 케어",
    "d7_active_days": "최근 7일 청취 급감 고객에게 개인화 추천 알림",
    "d30_active_days": "최근 30일 청취 감소 고객에게 개인화 추천 알림",
    "d90_active_days": "중기 청취 감소 고객에게 콘텐츠 추천 리마인드",
    "full_active_days": "저활동 고객 대상 온보딩 안내 강화",
    "trend_secs_recent15_vs_prior15": "청취량 급감 고객에게 개인화 추천 발송",
    "tenure_days": "신규 가입자 대상 온보딩 강화",
}


def load_final_meta():
    meta_path = MODELS_DIR / "lightgbm_enhanced_v2_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"최종 모델 메타데이터가 없습니다: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def export_model_stats(meta):
    comparison_path = MODELS_DIR / "model_comparison.csv"
    if comparison_path.exists():
        comparison = pd.read_csv(comparison_path)
        model_stats = comparison.loc[
            comparison["split"].eq("test"),
            ["model", "auc", "f1", "threshold"],
        ].rename(columns={"model": "model_name"})
        lightgbm_mask = model_stats["model_name"].eq("LightGBM")
        model_stats.loc[lightgbm_mask, ["auc", "f1", "threshold"]] = [
            meta["test_auc"],
            meta["test_f1"],
            meta["threshold"],
        ]
        if not lightgbm_mask.any():
            model_stats.loc[len(model_stats)] = [
                "LightGBM",
                meta["test_auc"],
                meta["test_f1"],
                meta["threshold"],
            ]
    else:
        model_stats = pd.DataFrame(
            [{
                "model_name": "LightGBM",
                "auc": meta["test_auc"],
                "f1": meta["test_f1"],
                "threshold": meta["threshold"],
            }]
        )

    model_stats.to_csv(OUT_DIR / "model_stats.csv", index=False)
    print(f"model_stats.csv ({len(model_stats)} rows)")


def load_shap_data(meta):
    model_path = MODELS_DIR / "lightgbm_enhanced_v2.txt"
    table_path = PROCESSED_DIR / meta["source_table"]
    if not model_path.exists() or not table_path.exists():
        raise FileNotFoundError(
            "SHAP 값을 계산할 최종 모델 또는 Enhanced v2 입력 테이블이 없습니다."
        )

    print("최종 Enhanced v2 모델에서 SHAP 표본을 생성합니다.")
    usecols = ["msno", "split", *meta["feature_cols"]]
    table = pd.read_csv(table_path, usecols=usecols, low_memory=False)
    sample_pool = table.loc[table["split"].eq("valid")]
    sample = sample_pool.sample(n=min(5_000, len(sample_pool)), random_state=42).copy()
    del table, sample_pool

    features = sample[meta["feature_cols"]].copy()
    for column in meta["categorical_cols"]:
        features[column] = features[column].astype("category")

    model = lgb.Booster(model_file=str(model_path))
    contributions = model.predict(
        features,
        pred_contrib=True,
        num_iteration=meta["best_iteration"],
    )
    probabilities = model.predict(
        features,
        num_iteration=meta["best_iteration"],
    )
    return {
        "msno": sample["msno"].to_numpy(),
        "feature_cols": meta["feature_cols"],
        "shap_values": contributions[:, :-1],
        "pred_proba": probabilities,
    }


def export_shap_importance(shap_data):
    importance = pd.DataFrame({
        "feature": shap_data["feature_cols"],
        "mean_abs_shap": np.abs(shap_data["shap_values"]).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False)
    importance["feature_ko"] = importance["feature"].map(
        lambda feature: DRIVER_KO.get(feature, feature)
    )
    importance = importance[["feature", "feature_ko", "mean_abs_shap"]]
    importance.to_csv(OUT_DIR / "shap_importance.csv", index=False)
    print(f"shap_importance.csv ({len(importance)} rows)")


def export_funnel():
    members = pd.read_csv(RAW_DIR / "members_v3.csv", usecols=["msno"])
    transactions = pd.read_csv(
        PROCESSED_DIR / "features_transactions.csv",
        usecols=["msno", "auto_renew_rate"],
    )
    logs = pd.read_csv(
        PROCESSED_DIR / "features_user_logs.csv",
        usecols=["msno", "full_active_days"],
    )
    labels = pd.read_csv(
        PROCESSED_DIR / "model_table_enhanced_v2.csv",
        usecols=["msno", "is_churn"],
    )

    stage1 = set(members["msno"])
    stage2 = stage1 & set(transactions["msno"])
    stage3 = stage2 & set(logs["msno"])
    stage4 = stage3 & set(logs.loc[logs["full_active_days"] >= 7, "msno"])
    stage5 = stage4 & set(
        transactions.loc[transactions["auto_renew_rate"] > 0, "msno"]
    )
    user_churn = labels.groupby("msno")["is_churn"].max()
    labeled = set(user_churn.index)
    retained = set(user_churn[user_churn == 0].index)
    stage6_denominator = stage5 & labeled
    stage6 = stage6_denominator & retained

    funnel = pd.DataFrame({
        "stage": [
            "1. 가입",
            "2. 첫 결제",
            "3. 이용",
            "4. 반복 이용",
            "5. 자동 갱신",
            "6. 재구독(라벨 코호트 한정)",
        ],
        "cnt": [
            len(stage1), len(stage2), len(stage3),
            len(stage4), len(stage5), len(stage6),
        ],
        "denominator": [
            np.nan, len(stage1), len(stage2),
            len(stage3), len(stage4), len(stage6_denominator),
        ],
    })
    funnel["stage_conversion_pct"] = (
        funnel["cnt"] / funnel["denominator"] * 100
    ).round(1)
    funnel["overall_pct"] = (funnel["cnt"] / len(stage1) * 100).round(1)
    funnel[["stage", "cnt", "stage_conversion_pct", "overall_pct"]].to_csv(
        OUT_DIR / "funnel_stats.csv",
        index=False,
    )
    print(f"funnel_stats.csv ({len(funnel)} rows)")


def export_segment_drivers(shap_data, threshold):
    shap_values = pd.DataFrame(
        shap_data["shap_values"],
        columns=shap_data["feature_cols"],
    )
    high_risk = np.asarray(shap_data["pred_proba"]) >= threshold
    high_risk_shap = shap_values.loc[high_risk]

    if high_risk_shap.empty:
        raise ValueError("최종 임계값 이상인 SHAP 표본이 없습니다.")

    drivers = high_risk_shap.idxmax(axis=1)
    table = drivers.value_counts().rename("cnt").to_frame()
    table["pct"] = (table["cnt"] / high_risk.sum() * 100).round(1)
    table["driver_ko"] = table.index.map(
        lambda feature: DRIVER_KO.get(feature, feature)
    )
    table["suggested_action"] = table.index.map(
        lambda feature: ACTION_MAP.get(feature, "개별 분석 필요")
    )
    table = table.reset_index().rename(columns={"index": "driver_feature"})
    table = table[
        ["driver_feature", "driver_ko", "cnt", "pct", "suggested_action"]
    ]
    table.to_csv(OUT_DIR / "segment_drivers.csv", index=False)
    print(f"segment_drivers.csv ({len(table)} rows)")


def export_retention_cohort():
    transaction_path = (RAW_DIR / "transactions.csv").as_posix()
    connection = duckdb.connect()
    try:
        cohort_raw = connection.sql(f"""
            WITH txn_months AS (
                SELECT DISTINCT
                    msno,
                    DATE_TRUNC(
                        'month',
                        STRPTIME(CAST(transaction_date AS VARCHAR), '%Y%m%d')
                    ) AS txn_month
                FROM read_csv_auto('{transaction_path}')
                WHERE transaction_date <= 20170131
            ),
            cohort AS (
                SELECT msno, MIN(txn_month) AS cohort_month
                FROM txn_months
                GROUP BY msno
            )
            SELECT
                cohort.cohort_month,
                DATE_DIFF('month', cohort.cohort_month, txn.txn_month) AS month_offset,
                COUNT(DISTINCT txn.msno) AS active_users
            FROM txn_months AS txn
            JOIN cohort USING (msno)
            WHERE DATE_DIFF('month', cohort.cohort_month, txn.txn_month) BETWEEN 0 AND 11
            GROUP BY cohort.cohort_month, month_offset
            ORDER BY cohort.cohort_month, month_offset
        """).df()
    finally:
        connection.close()

    cohort_sizes = cohort_raw.loc[
        cohort_raw["month_offset"].eq(0)
    ].set_index("cohort_month")["active_users"]
    cohort_raw["pct"] = (
        cohort_raw["active_users"]
        / cohort_raw["cohort_month"].map(cohort_sizes)
        * 100
    )
    latest_complete_cohort = (
        CUTOFF_DATE.to_period("M").to_timestamp() - pd.DateOffset(months=11)
    )
    result = cohort_raw.loc[
        cohort_raw["cohort_month"] <= latest_complete_cohort,
        ["cohort_month", "month_offset", "pct"],
    ].copy()
    result["cohort_month"] = result["cohort_month"].dt.strftime("%Y-%m")
    result["pct"] = result["pct"].round(4)
    result.to_csv(OUT_DIR / "retention_cohort.csv", index=False)
    print(f"retention_cohort.csv ({len(result)} rows)")


def main():
    meta = load_final_meta()
    shap_data = load_shap_data(meta)

    export_model_stats(meta)
    export_shap_importance(shap_data)
    export_funnel()
    export_segment_drivers(shap_data, meta["threshold"])
    export_retention_cohort()

    print(f"\n참조 테이블 5개 저장 완료 -> {OUT_DIR}")


if __name__ == "__main__":
    main()
