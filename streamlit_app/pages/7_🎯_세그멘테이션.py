import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GRID = "#e1e0d9"

st.set_page_config(page_title="세그멘테이션", page_icon="🎯", layout="wide")
apply_theme()
section_header(
    "Business Impact",
    "🎯 고위험 고객 세그멘테이션",
    "SHAP 값을 개별 피처 단위로 봐서, 고위험 고객 각각의 \"이탈 위험을 가장 크게 밀어올린 피처\"로 세그먼트를 만듭니다.",
)
st.warning("규칙 기반(SHAP 최댓값) 세그멘테이션입니다. 실제 원인이나 효과가 검증된 액션이 아니라 방향성 제안입니다.", icon="⚠️")

meta = json.loads((DATA_DIR / "segmentation_meta.json").read_text(encoding="utf-8"))
segmentation = pd.read_csv(DATA_DIR / "segmentation.csv")

st.metric("고위험 고객", f"{meta['high_risk_n']:,}명", f"샘플 {meta['sample_n']:,}명 중 {meta['high_risk_n']/meta['sample_n']*100:.1f}%")

fig = go.Figure(go.Bar(
    x=segmentation["count"], y=segmentation["driver_feature"], orientation="h", marker_color="#2a78d6",
    text=[f"{c}명 ({p}%)" for c, p in zip(segmentation["count"], segmentation["pct"])], textposition="outside",
))
fig.update_layout(template=get_plotly_template(), title="주요 이탈 동인별 고위험 고객 수", height=450)
st.plotly_chart(fig, width="stretch")

st.subheader("세그먼트별 제안 액션")
display = segmentation.rename(columns={
    "driver_feature": "주요 이탈 동인", "count": "고위험 고객 수", "pct": "비율(%)", "suggested_action": "제안 액션(미검증)",
})
st.dataframe(display, width="stretch", hide_index=True)

top_driver = segmentation.sort_values("count", ascending=False).iloc[0]
top_driver_text = f"{top_driver['driver_feature']} ({top_driver['pct']:.1f}%)"
st.markdown(f"가장 흔한 이탈 동인은 {highlight(top_driver_text)}입니다.", unsafe_allow_html=True)

next_page_link("pages/7_🎯_세그멘테이션.py")
