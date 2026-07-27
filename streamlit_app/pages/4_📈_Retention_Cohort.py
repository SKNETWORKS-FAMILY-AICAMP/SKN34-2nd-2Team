import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, get_plotly_template, section_header, next_page_link, highlight
from data_loader import load_csv, load_json

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

st.set_page_config(page_title="Retention & Cohort", page_icon="📈", layout="wide")
apply_theme()
section_header(
    "Product Analytics",
    "📈 Retention & Cohort",
    "첫 결제월 기준 코호트. 2015-01 ~ 2016-02 첫 결제 코호트만 표시 (12개월 관측 가능한 코호트).",
)
st.info("'활동' = 해당 월에 거래(transaction) 1건 이상. 자동갱신 청구 주기에 따라 실제보다 낮게 잡힐 수 있습니다.", icon="ℹ️")

retention = load_csv(DATA_DIR / "retention_cohort.csv").set_index("cohort_month")
retention.columns = [int(c) for c in retention.columns]

# 2015-01 코호트는 left-censored: cohort_month이 데이터 시작월(2015-01)부터만 관측 가능해서,
# 그 이전부터 활동하던 기존 유저까지 "신규 유입"으로 잡혀 M1 리텐션이 90%대로 다른 코호트
# (12~75%)와 이질적으로 높게 나온다. 히트맵에는 표시하되 라벨로 구분하고, 평균 곡선 계산에서는 제외한다.
LEFT_CENSORED_COHORT = "2015-01"
y_labels = [f"{c} (관측 불완전)" if c == LEFT_CENSORED_COHORT else c for c in retention.index]

fig = go.Figure(go.Heatmap(
    z=retention.values, x=[f"M{m + 1}" for m in retention.columns], y=y_labels,
    colorscale=[[0, "#cde2fb"], [0.5, "#3987e5"], [1, "#104281"]],
    zmin=0, zmax=100, colorbar=dict(title="리텐션(%)"),
    hovertemplate="코호트 %{y}, %{x}<br>리텐션: %{z:.1f}%<extra></extra>",
))
fig.update_layout(
    template=get_plotly_template(),
    title="코호트별 월간 리텐션 (%)", height=650, xaxis_title="첫 결제월 이후 경과 개월", yaxis_title="코호트 (첫 결제월)",
)
st.plotly_chart(fig, width="stretch")
st.caption(
    "2015-01 코호트는 관측 시작 이전부터 활동하던 유저까지 '신규'로 잡히는 left-censoring 때문에 "
    "리텐션이 이례적으로 높게 나와, 아래 평균 곡선/지표 계산에서는 제외했습니다."
)

st.subheader("전체 평균 리텐션 곡선")
avg_retention = retention.drop(index=LEFT_CENSORED_COHORT).mean(axis=0)
fig2 = go.Figure(go.Scatter(
    x=[f"M{m + 1}" for m in avg_retention.index], y=avg_retention.values,
    mode="lines+markers", line=dict(color="#2a78d6", width=3), marker=dict(size=8),
))
fig2.update_layout(
    template=get_plotly_template(),
    title="코호트 평균 리텐션 곡선", yaxis_title="평균 리텐션(%)", yaxis_range=[0, 100],
)
st.plotly_chart(fig2, width="stretch")

col1, col2, col3 = st.columns(3)
col1.metric("M2 리텐션", f"{avg_retention.get(1, float('nan')):.1f}%")
col2.metric("M7 리텐션", f"{avg_retention.get(6, float('nan')):.1f}%")
col3.metric("M12 리텐션", f"{avg_retention.get(11, float('nan')):.1f}%")

m11_text = f"약 {avg_retention.get(11, float('nan')):.0f}%"
st.markdown(f"1년 뒤에도 {highlight(m11_text)}의 유저가 여전히 활동합니다.", unsafe_allow_html=True)

st.divider()
st.subheader("🔎 2015-06 코호트만 리텐션이 유독 낮은 이유")
jun2015 = load_json(DATA_DIR / "jun2015_investigation.json")
cohort_df = pd.DataFrame(jun2015["cohorts"]).rename(columns={
    "cohort_month": "코호트월", "new_users": "신규 유저 수", "top_payment_method": "최다 결제수단 ID",
    "top_payment_method_pct": "최다 결제수단 비중(%)", "top_plan_days": "최빈 플랜일수", "avg_amount_paid": "평균 결제액(NTD)",
})
st.dataframe(cohort_df, width="stretch", hide_index=True)
zero_plan_rows = cohort_df.loc[cohort_df["최빈 플랜일수"] == 0, "코호트월"].tolist()
if zero_plan_rows:
    st.caption(
        f"ℹ️ {', '.join(zero_plan_rows)} 코호트의 '최빈 플랜일수'가 0으로 표시되는 건 원본 `transactions.csv`에 "
        "실제로 그렇게 기록된 값이며(0일짜리 결제 건이 최빈값), 집계 오류가 아닙니다."
    )
st.markdown(
    f"`transactions.csv`를 직접 재조회한 결과, 2015-06 코호트는 신규 유저가 **178,421명**으로 전월(약 4만 5천명)의 "
    f"약 4배로 급증했고, 그중 {highlight('81.7%가 결제수단 하나(ID 35)에 쏠렸으며, 최빈 플랜이 7일(초단기), 평균 결제액도 76.5 NTD로 다른 달의 1/3 수준')}"
    "이었습니다. 특정 채널을 통한 단기 체험/프로모션성 대량 가입 이벤트로 추정되며, 재구독 없이 대거 이탈해 이 코호트의 리텐션이 폭락한 것으로 보입니다.",
    unsafe_allow_html=True,
)
st.warning(
    f"다만 이건 **데이터에서 관찰된 패턴에 기반한 추정**입니다. 원본 데이터의 결제수단 ID는 익명화돼 있어 "
    "어떤 채널/제휴였는지 공식적으로 확인할 방법이 없고, 실제로 찾을 수 있었던 2015년 6월 KKBOX 공지 기사도 "
    f"이 급증과 직접적인 인과관계가 확인되지는 않았습니다: [{jun2015['news_reference']['title']}]({jun2015['news_reference']['url']}) — "
    f"{jun2015['news_reference']['note']}",
    icon="⚠️",
)

next_page_link("pages/4_📈_Retention_Cohort.py")
