import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COLORS = {"primary": "#2a78d6", "secondary": "#eb6834", "muted": "#898781", "grid": "#e1e0d9"}

st.set_page_config(page_title="EDA 개요", page_icon="📊", layout="wide")
apply_theme()
section_header("Data Foundations", "📊 EDA 개요", "`EDA/*.ipynb` 4개 노트북에서 검증한 원본 데이터 규모와 품질 이슈")

eda = json.loads((DATA_DIR / "eda_summary.json").read_text(encoding="utf-8"))

tab1, tab2, tab3 = st.tabs(["데이터 규모", "라벨(train/train_v2)", "데이터 품질 이슈"])

with tab1:
    rows = pd.DataFrame([
        {"파일": "members_v3.csv", "행 수": eda["members_v3"]["rows"]},
        {"파일": "transactions.csv", "행 수": eda["transactions"]["rows_dedup"]},
        {"파일": "user_logs.csv", "행 수": eda["user_logs"]["rows"]},
    ])
    fig = go.Figure(go.Bar(
        x=rows["파일"], y=rows["행 수"], marker_color=COLORS["primary"],
        text=[f"{v:,}" for v in rows["행 수"]], textposition="outside",
    ))
    fig.update_layout(
        template=get_plotly_template(),
        title="원본 파일별 행 수",
        yaxis=dict(title="행 수", type="log", dtick=1),
        margin=dict(t=70, l=10, r=10, b=60),
    )
    st.plotly_chart(fig, width="stretch")

with tab2:
    col1, col2 = st.columns(2)
    with col1:
        st.metric("train.csv (2017-02 만료 코호트)", f"{eda['train']['rows']:,}행",
                   f"이탈률 {eda['train']['churn_rate']*100:.1f}%")
    with col2:
        st.metric("train_v2.csv (2017-03 만료 코호트)", f"{eda['train_v2']['rows']:,}행",
                   f"이탈률 {eda['train_v2']['churn_rate']*100:.1f}%")

    st.metric("두 코호트 간 유저 중복", f"{eda['cohort_overlap_users']:,}명",
              f"겹치는 유저 라벨 일치율 {eda['label_agreement_rate']*100:.1f}%")
    st.markdown(
        f"중복 유저가 88~91%로 매우 높아, 시간 기반 분할 대신 {highlight('유저 그룹 기준 stratified 분할')}을 사용했습니다 "
        f"(최종 라벨 있는 유저 {eda['pooled_labeled_users']:,}명).",
        unsafe_allow_html=True,
    )

with tab3:
    st.markdown(
        f"""
- **members_v3**: 성별 결측 {eda['members_v3']['gender_missing_pct']:.1f}%, 나이 {eda['members_v3']['bd_invalid_pct']:.1f}%가 이상치(0 이하/100 초과)
- **transactions**: 완전 중복행 {eda['transactions']['duplicate_rows']:,}건 제거, 고유 유저 {eda['transactions']['unique_users']:,}명
- **user_logs**: `total_secs`에 음수/센티넬 손상값 소수 존재 (0.02% 미만), 청크 단위 1-pass 스캔으로 처리
        """
    )
    st.info("이런 이상치들은 preprocessing 단계에서 결정적 규칙으로 정제하고, 통계 기반 정제(결측 대체)는 train split으로만 학습했습니다.", icon="🧹")

next_page_link("pages/1_📊_EDA_개요.py")
