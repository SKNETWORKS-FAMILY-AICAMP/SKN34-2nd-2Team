-- "구독권 결제" 탭에 실제 마지막 결제 내역(결제 주기/정가/자동갱신 여부)을 보여주기 위한 컬럼 추가.
-- 값 자체는 build_scoring_table.py를 다시 돌려서 채워야 한다(features_transactions.csv의
-- last_payment_plan_days/last_plan_list_price/last_is_auto_renew를 그대로 가져옴).
-- 실행: mysql -u root -p kkbox_serving < backend/scoring/migrate_plan_fields.sql

USE kkbox_serving;

SET @col_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customer_churn_scores'
    AND column_name = 'last_payment_plan_days'
);

SET @add_cols_sql = IF(
  @col_exists = 0,
  'ALTER TABLE customer_churn_scores '
  'ADD COLUMN last_payment_plan_days INT NULL AFTER lifecycle_status, '
  'ADD COLUMN last_plan_list_price DECIMAL(10,2) NULL AFTER last_payment_plan_days, '
  'ADD COLUMN last_is_auto_renew TINYINT(1) NULL AFTER last_plan_list_price',
  'SELECT 1'
);

PREPARE add_cols_stmt FROM @add_cols_sql;
EXECUTE add_cols_stmt;
DEALLOCATE PREPARE add_cols_stmt;

-- scored_at도 스크립트 실행일이 아니라 실제 데이터 기준일(2017-01-31)로 맞춘다.
-- (days_to_expire/days_since_last_txn과 같은 기준일이어야 두 값을 같이 써도 말이 된다.)
UPDATE customer_churn_scores SET scored_at = '2017-01-31';
