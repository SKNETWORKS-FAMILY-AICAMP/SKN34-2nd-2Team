import math
import sys
from pathlib import Path

import streamlit as st
from scipy import stats

sys.path.append(str(Path(__file__).resolve().parent.parent))
from theme import apply_theme, section_header, next_page_link
from data_loader import load_text

DOC_PATH = Path(__file__).resolve().parent.parent / "data" / "07_ab_test_design.md"

st.set_page_config(page_title="A/B 테스트 설계", page_icon="🧪", layout="wide")
apply_theme()
section_header("Experiment Design", "🧪 A/B 테스트 설계 (미실행)")
st.error(
    "이 문서는 **실험 설계안**입니다. KKBox 실서비스에 접근할 수 없어 실제로 실험을 진행한 적이 없습니다. "
    "결과 수치는 실제 관측치가 아닙니다.",
    icon="🚫",
)

st.markdown(load_text(DOC_PATH))

st.divider()
st.subheader("📐 표본수 계산기 (직접 계산)")
st.caption("위 문서의 표본수 표와 동일한 공식(두 비율 z-검정, `scipy.stats`)을 그대로 사용해 실시간으로 재계산합니다.")

calc_col1, calc_col2 = st.columns(2)
with calc_col1:
    baseline_pct = st.slider("Control 베이스라인 비율 (%)", min_value=1.0, max_value=99.0, value=93.6, step=0.1)
    mde_pp = st.slider("최소 탐지 효과 MDE (%p)", min_value=0.5, max_value=30.0, value=2.0, step=0.5)
with calc_col2:
    alpha = st.select_slider("유의수준 α (양측)", options=[0.10, 0.05, 0.025, 0.01], value=0.05)
    power = st.slider("검정력 (Power)", min_value=0.70, max_value=0.95, value=0.80, step=0.05)

arm_choice = st.radio(
    "비교 구조",
    ["2-arm (Control vs Treatment 1개)", "3-arm (Control vs Treatment 2개, Bonferroni 보정)"],
    horizontal=True,
)
is_three_arm = arm_choice.startswith("3-arm")
effective_alpha = alpha / 2 if is_three_arm else alpha

p1 = baseline_pct / 100
mde = mde_pp / 100
p2 = min(p1 + mde, 0.999)
z_alpha = stats.norm.ppf(1 - effective_alpha / 2)
z_power = stats.norm.ppf(power)
n_per_group = math.ceil((z_alpha + z_power) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / mde**2)
n_groups = 3 if is_three_arm else 2

res_col1, res_col2, res_col3 = st.columns(3)
res_col1.metric("Treatment 가정 비율", f"{p2 * 100:.1f}%")
res_col2.metric("그룹당 필요 표본수", f"{n_per_group:,}명")
res_col3.metric(f"전체 필요 표본수 ({n_groups}개 그룹)", f"{n_per_group * n_groups:,}명")

if is_three_arm:
    st.caption(f"3-arm 다중비교 보정: α={alpha} → α/2={effective_alpha} 적용")

st.markdown('<p class="editorial-next-label">마지막 페이지입니다</p>', unsafe_allow_html=True)
st.page_link("Home.py", label="🎧 처음으로 돌아가기", icon="⬅️")
