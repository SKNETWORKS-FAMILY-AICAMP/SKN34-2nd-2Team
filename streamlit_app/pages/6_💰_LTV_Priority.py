import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="LTV & Priority", page_icon="💰", layout="wide")
apply_theme()
section_header(
    "Business Impact",
    "💰 LTV & Retention Priority",
    "근사 LTV × LightGBM 이탈확률로 \"누구를 먼저 케어해야 하는가\" 우선순위 매트릭스를 만듭니다.",
)
st.latex(r"LTV \approx \text{Average Monthly Revenue} \times \text{Expected Lifetime}")
st.warning(
    "LTV는 근사치입니다 (avg_monthly_revenue = 총결제액/결제횟수, "
    "expected_lifetime = 1/이탈확률의 상수 이탈률 근사, 상한 60개월). "
    "Kaplan-Meier 등 생존분석 기반 정밀 LTV가 아닙니다.",
    icon="⚠️",
)

ltv_summary = json.loads((DATA_DIR / "ltv_summary.json").read_text(encoding="utf-8"))
ltv_sample = pd.read_csv(DATA_DIR / "ltv_sample.csv")

SEGMENT_COLORS = {"고위험/고가치": "#e34948", "고위험/저가치": "#eda100", "저위험/고가치": "#1baf7a", "저위험/저가치": "#2a78d6"}

col1, col2, col3, col4 = st.columns(4)
counts = ltv_summary["segment_counts"]
for col, seg in zip([col1, col2, col3, col4], SEGMENT_COLORS):
    col.metric(seg, f"{counts.get(seg, 0):,}명")

tab2d, tab3d = st.tabs(["2D 매트릭스", "🌐 3D 인터랙티브 뷰"])

with tab2d:
    fig = px.scatter(
        ltv_sample, x="churn_proba", y="ltv_approx", color="segment",
        color_discrete_map=SEGMENT_COLORS, opacity=0.35,
        labels={"churn_proba": "예측 이탈확률", "ltv_approx": "근사 LTV (NTD)"},
        log_y=True,
    )
    fig.add_vline(x=ltv_summary["risk_threshold"], line_dash="dash", line_color="#898781")
    fig.update_layout(
        template=get_plotly_template(),
        title=f"Retention Priority 매트릭스 (샘플 {len(ltv_sample):,}명)",
        height=600,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, title_text=""),
        margin=dict(t=110, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, width="stretch")

with tab3d:
    st.caption("이탈확률 × 월평균매출 × 예상 잔존개월(3축)을 마우스로 회전/확대해서 볼 수 있습니다. 데이터는 왼쪽 2D 뷰와 동일합니다.")
    fig3d = go.Figure()
    for seg, color in SEGMENT_COLORS.items():
        sub = ltv_sample[ltv_sample["segment"] == seg]
        fig3d.add_trace(go.Scatter3d(
            x=sub["churn_proba"], y=sub["avg_monthly_revenue"], z=sub["expected_lifetime_months"],
            mode="markers", name=seg,
            marker=dict(size=2.5, color=color, opacity=0.5),
        ))
    fig3d.update_layout(
        template=get_plotly_template(),
        title=f"3D Retention Priority (샘플 {len(ltv_sample):,}명)",
        scene=dict(
            xaxis_title="이탈확률", yaxis_title="월평균매출(NTD)", zaxis_title="예상 잔존개월",
            bgcolor="#fcfcfb",
        ),
        height=650,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
            title_text="", bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=110, l=10, r=10, b=10),
    )
    st.plotly_chart(fig3d, width="stretch")

st.subheader("고위험/고가치 상위 20명 (예시)")
st.caption("실제 액션을 취한 것이 아니라 우선순위 후보군 식별 데모입니다.")
top_priority = pd.read_csv(DATA_DIR / "ltv_top_priority.csv")
st.dataframe(
    top_priority.style.format({
        "churn_proba": "{:.3f}", "avg_monthly_revenue": "{:,.0f}",
        "expected_lifetime_months": "{:.1f}", "ltv_approx": "{:,.0f}",
    }),
    width="stretch", hide_index=True,
)

st.markdown(
    f"이 {len(top_priority)}명은 {highlight('이탈확률과 결제액이 모두 높은')} 유저로, "
    "리텐션 액션의 우선순위 후보군입니다.",
    unsafe_allow_html=True,
)

next_page_link("pages/6_💰_LTV_Priority.py")
