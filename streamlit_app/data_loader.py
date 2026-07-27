"""
공통 데이터 로딩 유틸 — 모든 페이지가 여기를 통해 streamlit_app/data/ 파일을 읽는다.

- @st.cache_data로 캐싱해서 위젯 조작(슬라이더/라디오/탭 전환)마다 파일을 다시 읽지 않는다.
- 파일이 없으면(예: prepare_data.py를 아직 실행하지 않은 경우) 처리되지 않은 traceback 대신
  안내 메시지를 보여주고 스크립트 실행을 멈춘다.
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st


def _missing_file_stop(path: Path):
    st.error(
        f"데이터 파일이 없습니다: `{path.name}`. 프로젝트 루트에서 "
        "`python streamlit_app/prepare_data.py`를 먼저 실행해서 `streamlit_app/data/` 아래 "
        "파일들을 생성했는지 확인해주세요.",
        icon="🚫",
    )
    st.stop()


@st.cache_data
def load_csv(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        _missing_file_stop(path)
    return pd.read_csv(path, **kwargs)


@st.cache_data
def load_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        _missing_file_stop(path)
    return pd.read_parquet(path)


@st.cache_data
def load_json(path: Path) -> dict:
    if not path.exists():
        _missing_file_stop(path)
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data
def load_text(path: Path) -> str:
    if not path.exists():
        _missing_file_stop(path)
    return path.read_text(encoding="utf-8")
