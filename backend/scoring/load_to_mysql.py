"""
Phase 2 — Phase 1 산출물(backend/scoring/output/*.csv)을 MySQL(kkbox_serving)에 적재한다.

순서: DB 생성 -> schema.sql 실행 -> 기존 데이터 TRUNCATE -> customer_churn_scores +
참조 테이블 5개 적재 (staff_accounts/customer_actions는 건드리지 않음 — 계정/발송 기록은
그대로 유지)

재실행 시 이전 스코어링 결과 위에 새로 append되지 않도록, 테이블당 적재 직전에
TRUNCATE 후 새로 넣는다. 즉 이 스크립트를 다시 돌리면 "이전에 했던 건 삭제하고
새 결과로 교체"가 된다.

실행: python backend/scoring/load_to_mysql.py
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parent.parent))  # backend/db.py 임포트용
from db import get_engine, get_server_engine  # noqa: E402

SCORING_DIR = Path(__file__).resolve().parent
OUT_DIR = SCORING_DIR / "output"
SCHEMA_PATH = SCORING_DIR / "schema.sql"


def ensure_database():
    server_engine = get_server_engine()
    with server_engine.begin() as conn:
        conn.execute(text(
            "CREATE DATABASE IF NOT EXISTS kkbox_serving "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    print("DB 확인/생성 완료: kkbox_serving")


def run_schema(engine):
    sql_text = SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql_text.split(";") if s.strip() and not s.strip().startswith("--")]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    print(f"스키마 적용 완료 ({len(statements)}개 statement)")


def load_table(engine, csv_name, table_name, chunksize=None, truncate=True):
    path = OUT_DIR / csv_name
    if not path.exists():
        print(f"건너뜀 (파일 없음): {csv_name} — build_scoring_table.py / export_reference_tables.py 먼저 실행하세요")
        return
    if truncate:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name}"))
        print(f"  ({table_name} 기존 데이터 삭제 완료)")
    df = pd.read_csv(path)
    df.to_sql(table_name, engine, if_exists="append", index=False, chunksize=chunksize)
    print(f"적재 완료: {table_name} ({len(df):,} rows)")


def main():
    ensure_database()
    engine = get_engine()
    run_schema(engine)

    # 큰 테이블(99만 행)만 chunksize로, 나머지 소형 테이블은 한 번에.
    # customer_actions/staff_accounts는 여기서 건드리지 않음 — 실제 로그인 계정/발송 기록 보존.
    load_table(engine, "customer_churn_scores.csv", "customer_churn_scores", chunksize=5000)
    load_table(engine, "model_stats.csv", "model_stats")
    load_table(engine, "shap_importance.csv", "shap_importance")
    load_table(engine, "funnel_stats.csv", "funnel_stats")
    load_table(engine, "segment_drivers.csv", "segment_drivers")
    load_table(engine, "retention_cohort.csv", "retention_cohort")

    print("\n전체 적재 완료")


if __name__ == "__main__":
    main()
