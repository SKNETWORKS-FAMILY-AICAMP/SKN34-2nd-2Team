"""
[레거시/선택 실행] customer_churn_scores에 lifecycle_status 컬럼을 추가하고 값을 채운다.

이 스크립트가 필요했던 건 build_scoring_table.py가 lifecycle_status를 계산하기 전
시점의 데이터뿐이다. 지금은 build_scoring_table.py 5b단계가 이미 CSV에 lifecycle_status를
계산해 넣고 schema.sql의 CREATE TABLE도 그 컬럼을 이미 선언하고 있어서, load_to_mysql.py로
적재하면 이 스크립트 없이도 값이 정확히 채워진다 — 즉 build_scoring_table.py를 다시 돌려서
DB를 새로 적재한 이후로는 이 스크립트를 돌려도(같은 로직·같은 임계값이라) 결과가 달라지지
않는 중복 작업이다. build_scoring_table.py를 거치지 않고 옛날에 이미 적재된 DB에 컬럼만
급하게 채워야 하는 상황이 아니라면 실행할 필요 없음 — 참고용으로만 남겨둠.

모델을 다시 돌리거나 build_scoring_table.py를 재실행할 필요 없음 — 이미 있는
days_to_expire 값만으로 "구독 생애주기 상태"를 분류하는 순수 후처리 작업이다.
churn_proba / risk_tier / ltv_tier / segment 등 기존 모델 결과는 전혀 건드리지 않는다.

구독활성      : days_to_expire > 0
갱신유예기간   : -30 <= days_to_expire <= 0 (재구독 여부 아직 미확정, 긴급 갱신 대상)
장기만료      : days_to_expire < -30 (일반 Retention 대상에서 제외, Win-back 후보로 관리.
                "확정 이탈"이라고 단정하지 않는다 — 만료 후 실제 재구독 거래가 있었는지는
                아직 검증하지 않았기 때문. 대신 기존 ltv_tier로 고비용/저비용 win-back
                캠페인 후보만 나눈다.)
상태확인필요   : days_to_expire가 비어있는 경우

실행: python backend/scoring/add_lifecycle_status.py
(몇 번을 다시 실행해도 안전 — 컬럼 있으면 추가 안 하고, 값은 매번 새로 계산해서 덮어씀)
"""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parent.parent))  # backend/db.py 임포트용
from db import get_engine  # noqa: E402


def main():
    engine = get_engine()
    with engine.begin() as conn:
        cols = conn.execute(
            text("SHOW COLUMNS FROM customer_churn_scores LIKE 'lifecycle_status'")
        ).fetchall()
        if not cols:
            conn.execute(text("ALTER TABLE customer_churn_scores ADD COLUMN lifecycle_status VARCHAR(30)"))
            print("컬럼 추가 완료: lifecycle_status")
        else:
            print("컬럼 이미 존재: lifecycle_status (추가 건너뜀, 값만 갱신)")

        conn.execute(text(
            """
            UPDATE customer_churn_scores SET lifecycle_status =
                CASE
                    WHEN days_to_expire IS NULL THEN '상태확인필요'
                    WHEN days_to_expire > 0 THEN '구독활성'
                    WHEN days_to_expire BETWEEN -30 AND 0 THEN '갱신유예기간'
                    ELSE '장기만료'
                END
            """
        ))

        counts = conn.execute(text(
            "SELECT lifecycle_status, COUNT(*) AS cnt FROM customer_churn_scores "
            "GROUP BY lifecycle_status ORDER BY cnt DESC"
        )).mappings().all()

    print("업데이트 완료. 분포:")
    for row in counts:
        print(f"  {row['lifecycle_status']}: {row['cnt']:,}명")


if __name__ == "__main__":
    main()
