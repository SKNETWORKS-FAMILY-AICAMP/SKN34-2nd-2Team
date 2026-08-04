USE kkbox_serving;

CREATE TABLE IF NOT EXISTS campaigns (
  id                    BIGINT AUTO_INCREMENT PRIMARY KEY,
  request_key           VARCHAR(64) UNIQUE NOT NULL,
  name                  VARCHAR(120) NOT NULL,
  purpose               ENUM('retention','renewal','winback') NOT NULL,
  action_type           ENUM('reminder','discount_offer') NOT NULL,
  lifecycle_status      VARCHAR(30) NOT NULL,
  risk_tier             ENUM('고위험','저위험') NULL,
  segment               VARCHAR(20) NULL,
  selection_mode        ENUM('all_matching','top_n','manual') NOT NULL,
  audience_limit        INT NULL,
  exclude_recent_days   INT NOT NULL DEFAULT 7,
  matched_count         INT NOT NULL DEFAULT 0,
  excluded_count        INT NOT NULL DEFAULT 0,
  recipient_count       INT NOT NULL DEFAULT 0,
  status                ENUM('processing','completed','failed') NOT NULL DEFAULT 'processing',
  created_by            VARCHAR(255),
  created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
  launched_at           DATETIME NULL,
  INDEX idx_campaign_created (created_at),
  INDEX idx_campaign_status (status)
);

CREATE TABLE IF NOT EXISTS campaign_recipients (
  campaign_id      BIGINT NOT NULL,
  msno             VARCHAR(64) NOT NULL,
  group_type       ENUM('treatment','control') NOT NULL DEFAULT 'treatment',
  delivery_status  ENUM('recorded','failed') NOT NULL DEFAULT 'recorded',
  sent_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (campaign_id, msno),
  INDEX idx_campaign_recipient_msno (msno),
  CONSTRAINT fk_campaign_recipients_campaign
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

ALTER TABLE campaigns
  MODIFY COLUMN selection_mode ENUM('all_matching','top_n','manual') NOT NULL;

SET @campaign_column_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'customer_actions'
    AND column_name = 'campaign_id'
);

SET @add_campaign_column_sql = IF(
  @campaign_column_exists = 0,
  'ALTER TABLE customer_actions ADD COLUMN campaign_id BIGINT NULL AFTER msno, ADD INDEX idx_customer_action_campaign (campaign_id)',
  'SELECT 1'
);

PREPARE add_campaign_column_stmt FROM @add_campaign_column_sql;
EXECUTE add_campaign_column_stmt;
DEALLOCATE PREPARE add_campaign_column_stmt;
