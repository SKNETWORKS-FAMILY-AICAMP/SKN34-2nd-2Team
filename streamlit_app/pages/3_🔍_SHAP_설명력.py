import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight
from data_loader import load_csv, load_parquet

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="SHAP 설명력", page_icon="🔍", layout="wide")
apply_theme()
section_header(
    "Explainability",
    "🔍 SHAP 설명력 (XAI)",
    "test split 5,000명 샘플 기준. LightGBM 최종 모델(models/lightgbm_final.txt)에 SHAP TreeExplainer 적용.",
)
st.warning("SHAP은 모델이 예측 근거로 무엇을 반영했는지 보여주는 것이지, 실제 이탈의 인과적 원인을 증명하지 않습니다.", icon="⚠️")
st.caption(
    "ℹ️ TreeExplainer 계산 비용 때문에 test split(148,940명) 중 5,000명(약 3.4%)만 샘플링했습니다. "
    "전체 모집단의 분포와 다를 수 있습니다."
)

shap_importance = load_csv(DATA_DIR / "shap_importance.csv")
shap_df = load_parquet(DATA_DIR / "shap_sample.parquet")
feature_values_df = load_parquet(DATA_DIR / "shap_features.parquet")
feature_cols = [c for c in shap_df.columns if c not in ("msno", "pred_proba")]

tab1, tab2 = st.tabs(["전체 피처 중요도", "개별 고객 설명"])

with tab1:
    top_n = st.slider("표시할 피처 개수 (Top N)", min_value=5, max_value=len(shap_importance), value=15, step=1)
    top_features = shap_importance.head(top_n).sort_values("mean_abs_shap")
    fig = go.Figure(go.Bar(x=top_features["mean_abs_shap"], y=top_features["feature"], orientation="h", marker_color="#2a78d6"))
    fig.update_layout(template=get_plotly_template(), title=f"SHAP 평균 절댓값 기준 Top {top_n} 피처", height=max(550, 28 * top_n))
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        f"{highlight('결제/구독 상태 관련 피처')}(마지막 결제 정보, 자동갱신, 만료 임박 등)가 상위권을 차지합니다.",
        unsafe_allow_html=True,
    )
    st.caption(
        "ℹ️ 🤖 모델 비교 페이지의 gain 기준 중요도와 이 페이지의 SHAP 기준 중요도는 순위가 다를 수 있습니다 — "
        "둘 다 정상이며, 계산 방식이 다른 두 가지 관점(트리 분기 기여도 vs 예측값에 대한 기여도)일 뿐입니다."
    )

with tab2:
    ranked = shap_df[["msno", "pred_proba"]].sort_values("pred_proba", ascending=False).reset_index(drop=True)
    rank = st.number_input(
        f"예측 이탈확률 상위 몇 번째 고객을 볼까요? (샘플 {len(ranked):,}명 중)",
        min_value=1, max_value=len(ranked), value=1, step=1,
    )
    top_customer_msno = ranked.loc[rank - 1, "msno"]
    top_customer = shap_df.loc[shap_df["msno"] == top_customer_msno].iloc[0]
    customer_features = feature_values_df.loc[feature_values_df["msno"] == top_customer_msno].iloc[0]

    st.metric(f"고객 예측 이탈확률 (상위 {rank}번째)", f"{top_customer['pred_proba']:.4f}", delta_color="off")

    contrib = top_customer[feature_cols].sort_values(key=abs, ascending=False).head(10).sort_values()
    colors = ["#e34948" if v > 0 else "#2a78d6" for v in contrib.values]
    bar_labels = [f"{feat} = {customer_features[feat]:.2f}" for feat in contrib.index]
    fig2 = go.Figure(go.Bar(
        x=contrib.values, y=bar_labels, orientation="h", marker_color=colors,
        text=[f"{v:+.3f}" for v in contrib.values], textposition="outside",
    ))
    fig2.add_vline(x=0, line_color="#0b0b0b", line_width=1)
    fig2.update_layout(
        template=get_plotly_template(),
        title="이 고객의 이탈확률에 기여한 피처 Top 10 (SHAP value)",
        xaxis=dict(title="SHAP value (+ 위험 증가, - 위험 감소)"), height=500,
    )
    st.plotly_chart(fig2, width="stretch")
    st.caption("빨강 = 이탈 위험을 높이는 방향, 파랑 = 낮추는 방향. 막대 라벨은 '피처 = 실제 값'입니다.")

next_page_link("pages/3_🔍_SHAP_설명력.py")
