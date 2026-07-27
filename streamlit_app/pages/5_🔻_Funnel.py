import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight
from data_loader import load_csv

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="Funnel", page_icon="🔻", layout="wide")
apply_theme()
section_header(
    "Product Analytics",
    "🔻 고객 여정 퍼널",
    "1~5단계는 전체 회원(members_v3) 기준 순차 부분집합. 6단계(재구독)는 라벨 있는 코호트로 모집단이 축소됩니다.",
)

funnel = load_csv(DATA_DIR / "funnel.csv")

colors = ["#2a78d6"] * 5 + ["#eb6834"]
fig = go.Figure(go.Funnel(
    y=funnel["stage"], x=funnel["count"],
    textinfo="value+percent initial",
    marker=dict(color=colors),
))
fig.update_layout(template=get_plotly_template(), title="가입 → 재구독 퍼널", height=550)
st.plotly_chart(fig, width="stretch")

st.subheader("단계별 상세")
display_df = funnel.copy()
display_df["count"] = display_df["count"].map("{:,}".format)
display_df["stage_conversion_pct"] = display_df["stage_conversion_pct"].map(lambda v: f"{v:.1f}%" if pd.notna(v) else "-")
display_df["overall_pct"] = display_df["overall_pct"].map("{:.1f}%".format)
display_df.columns = ["단계", "인원수", "분모(직전 단계)", "직전 단계 대비 전환율", "전체 대비 비율"]
st.dataframe(display_df, width="stretch", hide_index=True)

st.warning(
    "6단계(재구독)는 다른 단계와 모집단이 다릅니다 (주황색 막대). 라벨이 있는 2월 만료 코호트로 한정된 결과입니다.",
    icon="⚠️",
)

weakest = funnel.dropna(subset=["stage_conversion_pct"]).sort_values("stage_conversion_pct").iloc[0]
weakest_text = f"{weakest['stage']} 단계 ({weakest['stage_conversion_pct']:.1f}%)"
st.markdown(f"가장 전환율이 낮은 구간은 {highlight(weakest_text)}입니다.", unsafe_allow_html=True)

next_page_link("pages/5_🔻_Funnel.py")
