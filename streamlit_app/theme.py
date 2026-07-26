"""
공통 시각 디자인 모듈 — "Editorial Data Story" 테마.

이 파일은 프레젠테이션(CSS/폰트/차트 크롬)만 담당한다. 데이터를 읽거나 계산하지 않는다.
각 페이지는 apply_theme()을 최상단에서 한 번 호출하고, 필요하면 section_header()로
제목/부제를 렌더링하고, Plotly 차트에는 get_plotly_template()을 적용한다.
"""
import plotly.graph_objects as go
import streamlit as st

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
HAIRLINE = "#e1e0d9"
HAIRLINE_STRONG = "#c3c2b7"
SURFACE = "#fcfcfb"
BG = "#f9f9f7"
ACCENT = "#2a78d6"

CATEGORICAL_COLORWAY = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

FONT_IMPORT_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700"
    "&family=Inter:wght@400;500;600;700&display=swap"
)

# 페이지 순서 (Home 포함) — next_page_link()에서 "다음 읽을거리" 계산에 사용
PAGES = [
    ("Home.py", "🎧 홈"),
    ("pages/1_📊_EDA_개요.py", "📊 EDA 개요"),
    ("pages/2_🤖_모델_비교.py", "🤖 모델 비교"),
    ("pages/3_🔍_SHAP_설명력.py", "🔍 SHAP 설명력"),
    ("pages/4_📈_Retention_Cohort.py", "📈 Retention & Cohort"),
    ("pages/5_🔻_Funnel.py", "🔻 Funnel"),
    ("pages/6_💰_LTV_Priority.py", "💰 LTV & Priority"),
    ("pages/7_🎯_세그멘테이션.py", "🎯 세그멘테이션"),
    ("pages/8_🧪_AB_테스트_설계.py", "🧪 A/B 테스트 설계"),
]


def apply_theme():
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: {INK};
        }}

        .stApp {{
            background-color: {BG};
        }}

        h1, h2, h3 {{
            font-family: 'Fraunces', Georgia, serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em;
            color: {INK} !important;
        }}

        [data-testid="stSidebar"] {{
            background-color: {SURFACE};
            border-right: 1px solid {HAIRLINE};
            font-family: 'Inter', sans-serif;
        }}

        [data-testid="stMetric"] {{
            background-color: {SURFACE};
            border: 1px solid {HAIRLINE};
            border-radius: 14px;
            padding: 1.1rem 1.3rem;
        }}
        [data-testid="stMetricValue"] {{
            font-family: 'Fraunces', Georgia, serif;
            font-weight: 600;
            color: {INK};
        }}
        [data-testid="stMetricLabel"] {{
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.72rem !important;
            color: {INK_MUTED} !important;
            font-weight: 600;
        }}

        hr {{
            border: none;
            border-top: 1px solid {HAIRLINE};
        }}

        [data-testid="stDataFrame"] {{
            border: 1px solid {HAIRLINE};
            border-radius: 12px;
            overflow: hidden;
        }}

        .editorial-eyebrow {{
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.75rem;
            font-weight: 600;
            color: {ACCENT};
            margin-bottom: 0.35rem;
        }}
        .editorial-title {{
            font-family: 'Fraunces', Georgia, serif;
            font-weight: 600;
            font-size: 2.6rem;
            line-height: 1.12;
            letter-spacing: -0.01em;
            color: {INK};
            margin: 0 0 0.6rem 0;
        }}
        .editorial-subtitle {{
            font-family: 'Inter', sans-serif;
            font-size: 1.05rem;
            color: {INK_SECONDARY};
            max-width: 68ch;
            margin: 0 0 1.1rem 0;
            line-height: 1.55;
        }}
        .editorial-rule {{
            border: none;
            border-top: 1px solid {HAIRLINE};
            margin: 0 0 1.6rem 0;
        }}

        [data-testid="stAlert"] {{
            border-radius: 12px;
            font-family: 'Inter', sans-serif;
        }}

        ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
        ::-webkit-scrollbar-track {{ background: {BG}; }}
        ::-webkit-scrollbar-thumb {{ background: {HAIRLINE_STRONG}; border-radius: 6px; }}

        /* --- 등장 애니메이션 (페이지 진입 시 한 번, fade + slide-up) --- */
        @keyframes editorialFadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .editorial-fade,
        [data-testid="stMetric"],
        [data-testid="stDataFrame"],
        [data-testid="stPlotlyChart"] {{
            animation: editorialFadeIn 0.55s cubic-bezier(0.2, 0.8, 0.2, 1) both;
        }}

        /* --- 호버 리프트: 정적 카드류만 (차트는 데이터 hover와 겹치지 않게 그림자만) --- */
        [data-testid="stMetric"], [data-testid="stDataFrame"] {{
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        [data-testid="stMetric"]:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 28px rgba(11, 11, 11, 0.08);
        }}
        [data-testid="stDataFrame"]:hover {{
            box-shadow: 0 10px 28px rgba(11, 11, 11, 0.06);
        }}
        [data-testid="stPlotlyChart"] {{
            border: 1px solid {HAIRLINE};
            border-radius: 12px;
            padding: 0.4rem;
            transition: box-shadow 0.2s ease;
        }}
        [data-testid="stPlotlyChart"]:hover {{
            box-shadow: 0 10px 28px rgba(11, 11, 11, 0.06);
        }}

        /* --- 형광펜 하이라이트 --- */
        mark.highlight {{
            background: linear-gradient(120deg, rgba(42,120,214,0.28) 0%, rgba(42,120,214,0.28) 100%);
            background-repeat: no-repeat;
            background-size: 100% 42%;
            background-position: 0 88%;
            color: {INK};
            font-weight: 600;
            padding: 0 0.15em;
        }}

        /* --- KPI 티커 배너 (CSS만으로 무한 스크롤) --- */
        .editorial-ticker {{
            overflow: hidden;
            white-space: nowrap;
            border-top: 1px solid {HAIRLINE};
            border-bottom: 1px solid {HAIRLINE};
            padding: 0.65rem 0;
            margin: 0.4rem 0 2.2rem 0;
            -webkit-mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
            mask-image: linear-gradient(90deg, transparent, #000 6%, #000 94%, transparent);
        }}
        .editorial-ticker-track {{
            display: inline-block;
            animation: tickerScroll 34s linear infinite;
        }}
        .editorial-ticker-track span {{
            display: inline-block;
            padding: 0 2.6rem;
            font-size: 0.92rem;
            color: {INK_SECONDARY};
            font-family: 'Inter', sans-serif;
        }}
        .editorial-ticker-track span b {{ color: {ACCENT}; }}
        @keyframes tickerScroll {{
            from {{ transform: translateX(0); }}
            to {{ transform: translateX(-50%); }}
        }}

        /* --- 다음 페이지 링크 카드 --- */
        .editorial-next-label {{
            text-transform: uppercase;
            letter-spacing: 0.14em;
            font-size: 0.72rem;
            font-weight: 600;
            color: {INK_MUTED};
            margin: 2.4rem 0 0.5rem 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def section_header(eyebrow: str, title: str, subtitle: str | None = None):
    """페이지 상단의 매거진 스타일 제목 블록. 기존 st.title/st.caption 텍스트를 그대로 받아 렌더링만 바꾼다.

    주의: 마크다운 파서가 HTML 블록 중간의 빈 줄을 블록 종료로 해석해서 그 뒤 내용을
    들여쓰기된 코드블록(리터럴 텍스트)으로 표시해버리는 문제가 있었다. subtitle이 없을 때
    빈 줄이 생기지 않도록, 줄 리스트를 만들어 빈 문자열 없이 join하는 방식으로 고쳤다.
    """
    lines = [
        '<div class="editorial-fade">',
        f'<p class="editorial-eyebrow">{eyebrow}</p>',
        f'<h1 class="editorial-title">{title}</h1>',
    ]
    if subtitle:
        lines.append(f'<p class="editorial-subtitle">{subtitle}</p>')
    lines.append('<hr class="editorial-rule" />')
    lines.append('</div>')
    st.markdown("\n".join(lines), unsafe_allow_html=True)


def get_plotly_template() -> go.layout.Template:
    """공통 라이트 Plotly 템플릿. 배경/그리드/폰트만 정의하며, 각 차트의 데이터 색상(marker_color,
    color_discrete_map 등)은 트레이스 단위로 지정된 값이 우선 적용되어 그대로 유지된다."""
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            font=dict(family="Inter, sans-serif", color=INK, size=13),
            title=dict(font=dict(family="Fraunces, Georgia, serif", size=20, color=INK)),
            xaxis=dict(gridcolor=HAIRLINE, zerolinecolor=HAIRLINE_STRONG, linecolor=HAIRLINE_STRONG),
            yaxis=dict(gridcolor=HAIRLINE, zerolinecolor=HAIRLINE_STRONG, linecolor=HAIRLINE_STRONG),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=INK_SECONDARY)),
            colorway=CATEGORICAL_COLORWAY,
            margin=dict(t=70, l=10, r=10, b=10),
        )
    )


def highlight(text: str) -> str:
    """형광펜 스타일로 강조할 텍스트 조각. 호출부의 st.markdown(..., unsafe_allow_html=True) 안에
    끼워 넣어 쓴다 (기존 문장의 단어를 바꾸지 않고 강조만 추가하는 용도)."""
    return f'<mark class="highlight">{text}</mark>'


def ticker_banner(items: list[str]):
    """검증된 사실들을 좌->우로 흐르는 CSS 전용 무한 스크롤 배너로 보여준다. JS 없이 순수 CSS 애니메이션."""
    spans = "".join(f"<span>{item}</span>" for item in items)
    # 이음새 없는 루프를 위해 내용을 두 번 이어붙이고 50% 지점에서 되돌아가게 한다
    st.markdown(
        f'<div class="editorial-ticker"><div class="editorial-ticker-track">{spans}{spans}</div></div>',
        unsafe_allow_html=True,
    )


def animated_metric(label: str, target: float, prefix: str = "", suffix: str = "", decimals: int = 0, height: int = 118):
    """0에서 target까지 카운트업되는 커스텀 지표 카드.

    st.metric은 순수 텍스트라 JS를 실행할 수 없어서, iframe 기반의 st.iframe으로 만든다
    (iframe 안의 <script>는 실제로 실행되지만, st.markdown에 넣은 <script>는 브라우저 보안 정책상
    실행되지 않는다는 제약이 있음).
    """
    html = f"""
    <html>
    <head>
        <link href="{FONT_IMPORT_URL}" rel="stylesheet">
        <style>
            body {{ margin: 0; }}
            .card {{
                font-family: 'Inter', sans-serif;
                background: {SURFACE};
                border: 1px solid {HAIRLINE};
                border-radius: 14px;
                padding: 1.1rem 1.3rem;
                box-sizing: border-box;
                overflow: hidden;
            }}
            .card-label {{
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-size: 0.72rem;
                color: {INK_MUTED};
                font-weight: 600;
                margin-bottom: 0.3rem;
                white-space: nowrap;
            }}
            .card-value {{
                font-family: 'Fraunces', Georgia, serif;
                font-weight: 600;
                font-size: clamp(1.05rem, 6.2vw, 2rem);
                color: {INK};
                white-space: nowrap;
                word-break: keep-all;
                overflow: hidden;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="card-label">{label}</div>
            <div class="card-value" id="val">{prefix}0{suffix}</div>
        </div>
        <script>
            const target = {target};
            const el = document.getElementById('val');
            const duration = 1100;
            const start = performance.now();
            function step(now) {{
                const p = Math.min((now - start) / duration, 1);
                const eased = 1 - Math.pow(1 - p, 3);
                const val = target * eased;
                el.textContent = "{prefix}" + val.toLocaleString(undefined, {{maximumFractionDigits: {decimals}, minimumFractionDigits: {decimals}}}) + "{suffix}";
                if (p < 1) requestAnimationFrame(step);
            }}
            requestAnimationFrame(step);
        </script>
    </body>
    </html>
    """
    st.iframe(html, height=height)


def next_page_link(current: str):
    """페이지 하단에 매거진 "다음 읽을거리" 스타일 링크를 붙인다. PAGES 순서 기준으로 다음 항목을 찾는다."""
    idx = next((i for i, (path, _) in enumerate(PAGES) if path == current), None)
    if idx is None or idx + 1 >= len(PAGES):
        return
    next_path, next_title = PAGES[idx + 1]
    st.markdown('<p class="editorial-next-label">다음 읽을거리</p>', unsafe_allow_html=True)
    st.page_link(next_path, label=next_title, icon="➡️")
