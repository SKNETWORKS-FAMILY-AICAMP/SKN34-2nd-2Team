import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
GRID = "#e1e0d9"

st.set_page_config(page_title="모델 비교", page_icon="🤖", layout="wide")
apply_theme()
section_header("Model Selection", "🤖 모델 비교", "같은 train/valid/test split(유저 그룹 stratified 70/15/15)으로 5개 모델을 학습·평가했습니다.")

comparison = pd.read_csv(DATA_DIR / "model_comparison.csv")
test_results = comparison[comparison["split"] == "test"].set_index("model")
test_results = test_results.sort_values("auc", ascending=False)

st.subheader("TEST 성능 비교")
metric_choice = st.radio("지표 선택", ["auc", "pr_auc", "f1", "precision", "recall", "logloss"], horizontal=True)

fig = go.Figure(go.Bar(
    x=test_results.index, y=test_results[metric_choice],
    marker_color=PALETTE[: len(test_results)],
    text=[f"{v:.4f}" for v in test_results[metric_choice]], textposition="outside",
))
fig.update_layout(
    template=get_plotly_template(),
    title=f"모델별 {metric_choice.upper()} (test)", yaxis_title=metric_choice.upper(),
)
st.plotly_chart(fig, width="stretch")

st.subheader("전체 지표 표")
BEST_CELL_STYLE = "background-color: rgba(42,120,214,0.35); font-weight: 600;"
metrics_table = test_results[["auc", "pr_auc", "logloss", "precision", "recall", "f1"]]
metrics_style = (
    metrics_table.style.format("{:.4f}")
    .highlight_max(subset=["auc", "pr_auc", "precision", "recall", "f1"], props=BEST_CELL_STYLE)
    .highlight_min(subset=["logloss"], props=BEST_CELL_STYLE)
)
st.dataframe(metrics_style, width="stretch")

st.markdown(
    f"""
**요약**: 트리 기반 모델(LightGBM/CatBoost/XGBoost/RandomForest) 4개는 AUC 0.93~0.94로 비슷한 성능대이고,
그중 {highlight('LightGBM이 근소하게 1위')}입니다. LogisticRegression은 확실히 뒤처지는데(AUC ~0.89), 이는 이 데이터에
비선형 관계가 많다는 것을 정량적으로 보여줍니다.
    """,
    unsafe_allow_html=True,
)

st.divider()
st.subheader("피처 중요도 (LightGBM, gain 기준)")
full_importance = pd.read_csv(DATA_DIR / "feature_importance.csv")
top_n = st.slider("표시할 피처 개수 (Top N)", min_value=5, max_value=len(full_importance), value=15, step=1)
importance = full_importance.head(top_n).sort_values("gain")
fig2 = go.Figure(go.Bar(x=importance["gain"], y=importance["feature"], orientation="h", marker_color="#2a78d6"))
fig2.update_layout(template=get_plotly_template(), title=f"Top {top_n} 피처 (gain)", height=max(500, 28 * top_n))
st.plotly_chart(fig2, width="stretch")

next_page_link("pages/2_🤖_모델_비교.py")
