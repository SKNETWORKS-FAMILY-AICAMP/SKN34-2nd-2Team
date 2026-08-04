"""
Phase 1b — 참조 테이블 5개를 schema.sql 컬럼 구조에 맞게 다시 저장한다.

v2(누수 수정) 파이프라인이 만든 data/dashboard/*.csv를 그대로 재사용한다 — 다시 계산하지 않음.
컬럼 이름/형태만 MySQL 테이블에 맞게 맞춘다.

단, model_stats(모델 비교표)만 예외로 streamlit_app/data/model_comparison.csv를 그대로 쓴다 —
이건 LightGBM/XGBoost/CatBoost/RandomForest/LogisticRegression "알고리즘 간" 비교표라 v1/v2
파이프라인 교체와 무관하고, 실제로 다시 계산된 적이 없다(교체 대상 아님).

다만 관리자 대시보드에서 "지금 서빙 중인 모델 성능"으로 오해되기 쉬웠던 LightGBM 행만은,
저장 직전에 models/lightgbm_enhanced_v2_meta.json의 실제 v2 서빙 값(test_auc/test_f1/threshold)으로
덮어쓴다. 나머지 4개 알고리즘 행은 그대로 구버전(누수 수정 전) 비교표 값이다 — "5개 알고리즘 동일 기준
비교"라는 원래 목적은 이 한 줄만큼은 깨지는 셈이지만, 관리자 화면에 실제와 다른 AUC가 뜨는 것보다는
낫다고 판단해 이렇게 처리한다.

실행: python backend/scoring/export_reference_tables.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
DASH_DATA = ROOT / "data" / "dashboard"
LEGACY_DASH_DATA = ROOT / "streamlit_app" / "data"  # model_comparison.csv 전용 (교체 대상 아님)
MODELS_DIR = ROOT / "models"
OUT_DIR = Path(__file__).resolve().parent / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DRIVER_KO = {
    "days_to_expire": "만료 임박",
    "days_since_last_txn": "장기 미결제",
    "last_is_auto_renew": "자동갱신 해제",
    "cancel_rate": "취소 이력",
    "auto_renew_rate": "자동갱신 낮음",
    "last_actual_amount_paid": "결제액 하락",
}


def main():
    # 1) model_stats — LightGBM/XGBoost/... test 행만 (실서비스는 채택 모델만 보여주면 되지만,
    #    운영 대시보드 "모델 비교" 탭에서 5개 다 보여주는 중이므로 test split만 남긴다)
    mc = pd.read_csv(LEGACY_DASH_DATA / "model_comparison.csv")
    model_stats = mc[mc["split"] == "test"][["model", "auc", "f1", "threshold"]].rename(
        columns={"model": "model_name"}
    )

    v2_meta_path = MODELS_DIR / "lightgbm_enhanced_v2_meta.json"
    if v2_meta_path.exists():
        v2_meta = json.loads(v2_meta_path.read_text(encoding="utf-8"))
        model_stats.loc[
            model_stats["model_name"] == "LightGBM", ["auc", "f1", "threshold"]
        ] = [v2_meta["test_auc"], v2_meta["test_f1"], v2_meta["threshold"]]
        print(
            f"  -> LightGBM 행을 실제 서빙 중인 v2 모델 값으로 덮어씀 "
            f"(auc={v2_meta['test_auc']:.4f}, threshold={v2_meta['threshold']:.4f})"
        )
    else:
        print(f"  [경고] {v2_meta_path} 없음 — LightGBM 행이 여전히 구버전(v1) 비교표 값입니다")

    model_stats.to_csv(OUT_DIR / "model_stats.csv", index=False)
    print(f"model_stats.csv ({len(model_stats)} rows)")

    # 2) shap_importance — 그대로 사용, feature_ko만 추가
    shap_imp = pd.read_csv(DASH_DATA / "shap_importance.csv")
    shap_imp["feature_ko"] = shap_imp["feature"].map(lambda f: DRIVER_KO.get(f, f))
    shap_imp = shap_imp[["feature", "feature_ko", "mean_abs_shap"]]
    shap_imp.to_csv(OUT_DIR / "shap_importance.csv", index=False)
    print(f"shap_importance.csv ({len(shap_imp)} rows)")

    # 3) funnel_stats
    funnel = pd.read_csv(DASH_DATA / "funnel.csv")
    funnel = funnel.rename(columns={"count": "cnt"})[
        ["stage", "cnt", "stage_conversion_pct", "overall_pct"]
    ]
    funnel.to_csv(OUT_DIR / "funnel_stats.csv", index=False)
    print(f"funnel_stats.csv ({len(funnel)} rows)")

    # 4) segment_drivers
    seg = pd.read_csv(DASH_DATA / "segmentation.csv")
    seg["driver_ko"] = seg["driver_feature"].map(lambda f: DRIVER_KO.get(f, f))
    seg = seg[["driver_feature", "driver_ko", "count", "pct", "suggested_action"]].rename(
        columns={"count": "cnt"}
    )
    seg.to_csv(OUT_DIR / "segment_drivers.csv", index=False)
    print(f"segment_drivers.csv ({len(seg)} rows)")

    # 5) retention_cohort — wide(0~11 컬럼) -> long(cohort_month, month_offset, pct)
    ret = pd.read_csv(DASH_DATA / "retention_cohort.csv")
    ret_long = ret.melt(id_vars="cohort_month", var_name="month_offset", value_name="pct")
    ret_long["month_offset"] = ret_long["month_offset"].astype(int)
    ret_long = ret_long.dropna(subset=["pct"]).sort_values(["cohort_month", "month_offset"])
    ret_long.to_csv(OUT_DIR / "retention_cohort.csv", index=False)
    print(f"retention_cohort.csv ({len(ret_long)} rows, long format)")

    print("\n참조 테이블 5개 저장 완료 ->", OUT_DIR)


if __name__ == "__main__":
    main()
