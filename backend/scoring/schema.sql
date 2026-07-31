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
  scored_at                 DATE NOT NULL,
  INDEX idx_risk (risk_tier),
  INDEX idx_segment (segment)
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
