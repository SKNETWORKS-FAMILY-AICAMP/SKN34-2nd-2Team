import json
from pathlib import Path

import pandas as pd
import streamlit as st

from theme import apply_theme, section_header, ticker_banner, animated_metric, next_page_link

DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="KKBOX 이탈 예측 프로젝트", page_icon="🎧", layout="wide")
apply_theme()

COLORS = {
    "primary": "#2a78d6",
    "secondary": "#eb6834",
    "good": "#0ca30c",
    "critical": "#d03b3b",
    "muted": "#898781",
}

section_header(
    "Churn Prediction",
    "🎧 KKBOX 고객 이탈(Churn) 예측 프로젝트",
    "대만 음악 스트리밍 서비스인 KKBOX의 2015~2017년 실제 데이터를 기반으로 하지만, "
    "실시간·최근 데이터는 아닙니다. 데이터 출처: "
    '<a href="https://www.kaggle.com/competitions/kkbox-churn-prediction-challenge/data" '
    'target="_blank" rel="noopener">Kaggle - WSDM KKBox\'s Churn Prediction Challenge</a>',
)

eda = json.loads((DATA_DIR / "eda_summary.json").read_text(encoding="utf-8"))

# 이미 검증된 수치들 (modeling/02_optuna_tuning, analytics/01_sql_feature_mart에서 확인된 값)
MODEL_TEST_AUC = 0.9434
SQL_SPEEDUP_X = 17.4  # DuckDB 104.5s vs pandas 청크 1820s

ticker_banner([
    f"🎧 라벨 있는 유저 <b>{eda['pooled_labeled_users']:,}</b>명",
    f"💳 결제 기록 <b>{eda['transactions']['rows_dedup']:,}</b>행",
    f"🎵 청취 로그 <b>{eda['user_logs']['size_gb']}GB</b> / <b>{eda['user_logs']['rows']:,}</b>행",
    f"🤖 LightGBM test AUC <b>{MODEL_TEST_AUC}</b>",
    f"⚡ DuckDB, pandas 청크 대비 <b>{SQL_SPEEDUP_X:.1f}배</b> 빠른 처리",
    f"🎯 최종 모델 판단 threshold <b>{eda['risk_threshold']:.3f}</b>",
])

st.subheader("프로젝트 한눈에 보기")
col1, col2, col3, col4 = st.columns(4)
with col1:
    animated_metric("라벨 있는 유저", eda["pooled_labeled_users"], suffix="명")
with col2:
    animated_metric("원본 결제 기록", eda["transactions"]["rows_dedup"], suffix="행")
with col3:
    animated_metric("청취 로그", eda["user_logs"]["rows"], suffix="행")
with col4:
    animated_metric("모델 판단 threshold", eda["risk_threshold"], decimals=3)

st.divider()

st.subheader("파이프라인 구조")
st.markdown(
    """
```
data/raw/ (원본 5개 CSV)
   ↓
EDA/            데이터 탐색 (4개 노트북)
   ↓
preprocessing/  피처엔지니어링 + 유저 그룹 분할 (6개 노트북)
   ↓
modeling/       LightGBM 등 5개 모델 학습·비교 (3개 노트북)
   ↓
analytics/      SQL 검증 + Retention/Cohort/Funnel/LTV + SHAP + 세그멘테이션 + A/B 설계 (7개 산출물)
   ↓
streamlit_app/  ← 지금 보고 계신 대시보드
```
    """
)

st.subheader("이 대시보드의 페이지")
st.markdown(
    """
- **📊 EDA 개요**: 원본 데이터 규모와 품질 이슈
- **🤖 모델 비교**: LightGBM / XGBoost / CatBoost / RandomForest / LogisticRegression 성능 비교
- **🔍 SHAP 설명력**: 모델이 무엇을 근거로 이탈을 예측하는지
- **📈 Retention & Cohort**: 코호트별 월간 리텐션
- **🔻 Funnel**: 가입부터 재구독까지 전환 퍼널
- **💰 LTV & Priority**: 근사 LTV와 Retention Priority 매트릭스
- **🎯 세그멘테이션**: 고위험 고객의 이탈 동인별 세그먼트
- **🧪 A/B 테스트 설계**: 세그멘테이션 결과 기반 실험 설계안 (미실행)
    """
)

st.info(
    "왼쪽 사이드바에서 페이지를 선택해 이동하세요. 모든 수치는 관련 노트북에서 이미 검증된 결과를 "
    "재사용합니다.",
    icon="👈",
)

next_page_link("Home.py")
