import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight
from data_loader import load_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PRIMARY_COLOR = "#2a78d6"

st.set_page_config(page_title="EDA 개요", page_icon="📊", layout="wide")
apply_theme()
section_header("Data Foundations", "📊 EDA 개요", "`EDA/*.ipynb` 4개 노트북에서 검증한 원본 데이터 규모와 품질 이슈")

eda = load_json(DATA_DIR / "eda_summary.json")

tab1, tab2, tab3 = st.tabs(["데이터 규모", "라벨(train.csv)", "데이터 품질 이슈"])

with tab1:
    rows = pd.DataFrame([
        {"파일": "members_v3.csv", "행 수": eda["members_v3"]["rows"]},
        {"파일": "transactions.csv", "행 수": eda["transactions"]["rows_dedup"]},
        {"파일": "user_logs.csv", "행 수": eda["user_logs"]["rows"]},
    ])
    fig = go.Figure(go.Bar(
        x=rows["파일"], y=rows["행 수"], marker_color=PRIMARY_COLOR,
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
    v2 = eda["train_v2_removed"]
    st.metric("train.csv (2017-02 만료 코호트)", f"{eda['train']['rows']:,}행",
               f"이탈률 {eda['train']['churn_rate']*100:.1f}%", delta_color="off")

    st.markdown(
        f"원래는 `train_v2.csv`(2017-03 만료 코호트, {v2['rows']:,}행, 이탈률 {v2['churn_rate']*100:.1f}%)를 "
        f"함께 풀링해서 썼습니다. 그런데 raw 데이터에 3월 실적 원본(`transactions_v2.csv`/`user_logs_v2.csv`)이 "
        f"없어 3월 코호트의 피처를 실제 3월 말 기준으로 계산할 방법이 없었고, 두 코호트를 msno 기준으로만 "
        f"병합한 결과 겹치는 유저 {v2['cohort_overlap_users']:,}명 중 라벨 불일치가 "
        f"{v2['label_conflict_users']:,}명(일치율 {v2['label_agreement_rate']*100:.1f}%)이나 발생했습니다 — "
        f"즉 {highlight('동일한 피처값에 서로 다른 정답이 붙는 문제')}가 있어, `train_v2.csv`를 제거하고 "
        f"`train.csv` 단일 코호트만 사용하도록 정리했습니다. "
        f"(유저 1명당 라벨이 1개뿐이라, stratified 분할이 곧 유저 그룹 분할입니다.)",
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
