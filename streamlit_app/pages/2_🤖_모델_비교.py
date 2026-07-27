import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight
from data_loader import load_csv

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]

st.set_page_config(page_title="모델 비교", page_icon="🤖", layout="wide")
apply_theme()
section_header("Model Selection", "🤖 모델 비교", "같은 train/valid/test split(유저 그룹 stratified 70/15/15)으로 5개 모델을 학습·평가했습니다.")

comparison = load_csv(DATA_DIR / "model_comparison.csv")
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
st.caption(
    "⚠️ LogLoss는 직접 비교가 부적절합니다: LightGBM은 클래스 재조정 없이 학습했고 나머지 4개 모델은 "
    "`class_weight`/`scale_pos_weight` 등으로 재조정해서 학습해, 두 그룹의 예측 확률 스케일(자연 분포 vs "
    "인위적으로 끌어올린 분포)이 달라 LogLoss가 낮게/높게 나오는 정도에 영향을 줍니다. AUC/PR-AUC/F1은 "
    "임계값·스케일에 덜 민감해 모델 간 비교에 더 적합합니다."
)

st.subheader("오버피팅 점검 (Train vs Test)")
train_results = comparison[comparison["split"] == "train"].set_index("model")
gap_df = (
    train_results[["auc"]].rename(columns={"auc": "train_auc"})
    .join(test_results[["auc"]].rename(columns={"auc": "test_auc"}))
    .assign(gap=lambda d: d["train_auc"] - d["test_auc"])
    .sort_values("test_auc", ascending=False)
)

fig_gap = go.Figure()
fig_gap.add_trace(go.Bar(x=gap_df.index, y=gap_df["train_auc"], name="Train AUC", marker_color="#898781"))
fig_gap.add_trace(go.Bar(x=gap_df.index, y=gap_df["test_auc"], name="Test AUC", marker_color="#2a78d6"))
fig_gap.update_layout(
    template=get_plotly_template(),
    title="모델별 Train vs Test AUC (차이가 크면 오버피팅 의심)",
    yaxis_title="AUC", yaxis_range=[0.9, 1.0], barmode="group",
)
st.plotly_chart(fig_gap, width="stretch")
st.dataframe(gap_df.style.format("{:.4f}"), width="stretch")
st.caption(
    "Train-Test AUC 차이가 5개 모델 전부 1%p 미만입니다. 오버피팅이 심하면 보통 train AUC가 0.999에 "
    "가까운데 test는 크게 떨어지는 패턴(수 %p~10%p 이상 차이)이 나타나는데, 여기선 그런 패턴이 보이지 "
    "않습니다 — test AUC가 이미 0.99대로 높은 건 오버피팅이 아니라 recency 피처(예: `days_to_expire`)가 "
    "실제로 강한 신호이기 때문일 가능성이 큽니다 (🔍 SHAP 설명력 페이지에서 이 피처의 기여도를 확인할 수 "
    "있습니다)."
)

top_auc_model = test_results.index[0]
st.markdown(
    f"""
**요약**: 트리 기반 모델(LightGBM/CatBoost/XGBoost/RandomForest) 4개는 AUC 0.98~0.99대로 비슷한 성능대이고,
그중 {highlight(f"{top_auc_model}이 근소하게 1위")}입니다. LogisticRegression은 확실히 뒤처지는데(AUC ~0.96),
이는 이 데이터에 비선형 관계가 많다는 것을 정량적으로 보여줍니다. 이후 SHAP/LTV/세그멘테이션 분석에는
AUC·PR-AUC 기준 최상위인 **LightGBM**을 최종 모델로 채택해 계속 사용합니다(AUC 차이가 근소해 어떤
트리 모델을 골라도 결론이 크게 달라지진 않습니다).
    """,
    unsafe_allow_html=True,
)

st.divider()
st.subheader("피처 중요도 (LightGBM, gain 기준)")
full_importance = load_csv(DATA_DIR / "feature_importance.csv")
top_n = st.slider("표시할 피처 개수 (Top N)", min_value=5, max_value=len(full_importance), value=15, step=1)
importance = full_importance.head(top_n).sort_values("gain")
fig2 = go.Figure(go.Bar(x=importance["gain"], y=importance["feature"], orientation="h", marker_color="#2a78d6"))
fig2.update_layout(template=get_plotly_template(), title=f"Top {top_n} 피처 (gain)", height=max(500, 28 * top_n))
st.plotly_chart(fig2, width="stretch")

next_page_link("pages/2_🤖_모델_비교.py")
