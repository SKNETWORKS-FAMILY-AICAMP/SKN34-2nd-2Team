-- 알림함 읽음 처리 + 고객 셀프 혜택 수령(콘서트 추첨 응모/갱신 즉시 리워드 등) 기능을 위한 컬럼 추가.
-- backend/scoring/migrate_campaigns.sql 과 동일하게, 이미 컬럼이 있으면 건너뛰는 안전한 방식으로 작성.
-- 실행: mysql -u root -p kkbox_serving < backend/scoring/migrate_notifications.sql

USE kkbox_serving;

SET @is_read_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customer_actions'
    AND column_name = 'is_read'
);

SET @add_is_read_sql = IF(
  @is_read_exists = 0,
  'ALTER TABLE customer_actions ADD COLUMN is_read TINYINT(1) NOT NULL DEFAULT 0 AFTER action_type',
  'SELECT 1'
);

PREPARE add_is_read_stmt FROM @add_is_read_sql;
EXECUTE add_is_read_stmt;
DEALLOCATE PREPARE add_is_read_stmt;

SET @benefit_key_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customer_actions'
    AND column_name = 'benefit_key'
);

-- benefit_key: 관리자가 보낸 일반 리마인드/오퍼는 NULL로 남고, 고객이 앱에서 직접 응모/수령한
-- 혜택(콘서트 티켓 추첨, 연차 혜택, 갱신 즉시 리워드)만 어떤 혜택인지 식별할 수 있도록 채워진다.
SET @add_benefit_key_sql = IF(
  @benefit_key_exists = 0,
  'ALTER TABLE customer_actions ADD COLUMN benefit_key VARCHAR(40) NULL AFTER is_read',
  'SELECT 1'
);

PREPARE add_benefit_key_stmt FROM @add_benefit_key_sql;
EXECUTE add_benefit_key_stmt;
DEALLOCATE PREPARE add_benefit_key_stmt;
