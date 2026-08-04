-- Phase 2 — 서빙용 MySQL 스키마
-- raw csv(members/transactions/user_logs/train)는 여기 포함되지 않음.
-- 이 DB에는 "모델 예측 결과 + 참조 테이블 + 계정"만 올라간다.
-- customer_churn_scores는 개별 고객 driver_feature(이유)를 넣지 않는다 —
-- 관리자 페이지는 코호트/세그먼트별 "리스트"만 필요하고, 이유별 집계는
-- segment_drivers 테이블(아래)로 충분하기 때문.

CREATE DATABASE IF NOT EXISTS kkbox_serving CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE kkbox_serving;

CREATE TABLE IF NOT EXISTS customer_churn_scores (
  msno                      VARCHAR(64) PRIMARY KEY,
  churn_proba               DECIMAL(6,5) NOT NULL,
  risk_tier                 ENUM('고위험','저위험') NOT NULL,
  ltv_tier                  ENUM('고가치','저가치') NOT NULL,
  segment                   VARCHAR(20) NOT NULL,
  avg_monthly_revenue       DECIMAL(10,2),
  expected_lifetime_months  DECIMAL(6,2),
  ltv_approx                DECIMAL(12,2),
  days_to_expire            INT,
  days_since_last_txn       INT,
  lifecycle_status          VARCHAR(30),
  scored_at                 DATE NOT NULL,
  INDEX idx_risk (risk_tier),
  INDEX idx_segment (segment),
  INDEX idx_lifecycle (lifecycle_status)
);

CREATE TABLE IF NOT EXISTS staff_accounts (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  email         VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  name          VARCHAR(100),
  role          ENUM('admin','staff') DEFAULT 'staff',
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_stats (
  model_name VARCHAR(50) PRIMARY KEY,
  auc        DECIMAL(6,4),
  f1         DECIMAL(6,4),
  threshold  DECIMAL(6,4)
);

CREATE TABLE IF NOT EXISTS shap_importance (
  feature        VARCHAR(64) PRIMARY KEY,
  feature_ko     VARCHAR(64),
  mean_abs_shap  DECIMAL(10,6)
);

CREATE TABLE IF NOT EXISTS funnel_stats (
  stage                 VARCHAR(50) PRIMARY KEY,
  cnt                   INT,
  stage_conversion_pct  DECIMAL(5,1),
  overall_pct           DECIMAL(5,1)
);

-- 개별 고객이 아니라 "고위험 그룹 전체"를 놓고 이유별로 집계한 리스트.
-- 관리자 페이지에서 원하는 건 이 테이블 하나로 충분하다.
CREATE TABLE IF NOT EXISTS segment_drivers (
  driver_feature     VARCHAR(64) PRIMARY KEY,
  driver_ko          VARCHAR(64),
  cnt                INT,
  pct                DECIMAL(5,1),
  suggested_action   VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS retention_cohort (
  cohort_month  VARCHAR(7),
  month_offset  INT,
  pct           DECIMAL(5,1),
  PRIMARY KEY (cohort_month, month_offset)
);

-- 고객군 단위 캠페인. 조건과 실행 당시 모집단/제외/최종 대상 수를 함께 보존해
-- 나중에도 "누구를 어떤 기준으로 선택했는지" 재현할 수 있게 한다.
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

-- 관리자가 개별 고객에게 보낸 액션(발표 데모용) — "리마인드 발송"/"할인 오퍼 발송" 버튼을
-- 누르면 여기 기록되고, 그 msno로 고객이 로그인하면 GET /me/actions로 조회해서
-- 소비자 앱 알림함에 보여준다. 실제 이메일/푸시 발송은 하지 않음.
CREATE TABLE IF NOT EXISTS customer_actions (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  msno        VARCHAR(64) NOT NULL,
  campaign_id BIGINT NULL,
  action_type ENUM('reminder','discount_offer') NOT NULL,
  sent_by     VARCHAR(255),
  sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_msno (msno),
  INDEX idx_customer_action_campaign (campaign_id)
);
