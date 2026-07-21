ALTER TABLE payment_transactions
  ADD COLUMN order_id VARCHAR(100) NULL,
  ADD COLUMN listing_id VARCHAR(100) NULL,
  ADD COLUMN subscription_plan_id VARCHAR(100) NULL,
  ADD COLUMN payment_type VARCHAR(50) NULL,
  ADD COLUMN gateway_tracking_id VARCHAR(100) NULL,
  ADD COLUMN bank_reference_number VARCHAR(100) NULL,
  ADD COLUMN order_status VARCHAR(50) NULL,
  ADD COLUMN payment_mode VARCHAR(100) NULL,
  ADD COLUMN failure_message TEXT NULL,
  ADD COLUMN status_code VARCHAR(50) NULL,
  ADD COLUMN status_message TEXT NULL,
  ADD COLUMN raw_response_json JSON NULL,
  ADD COLUMN initiated_at DATETIME NULL,
  ADD COLUMN completed_at DATETIME NULL,
  ADD COLUMN activated_at DATETIME NULL;

ALTER TABLE payment_transactions
  MODIFY amount DECIMAL(12,2) NOT NULL,
  MODIFY plan_id VARCHAR(100) NULL,
  MODIFY plan_name VARCHAR(255) NULL,
  MODIFY payment_gateway VARCHAR(30) NOT NULL DEFAULT 'ccavenue',
  MODIFY status ENUM('PENDING','SUCCESS','FAILED','ABORTED','INVALID','AWAITED') DEFAULT 'PENDING';

CREATE UNIQUE INDEX ix_payment_transactions_order_id ON payment_transactions (order_id);
CREATE INDEX ix_payment_transactions_user_id ON payment_transactions (user_id);
CREATE INDEX ix_payment_transactions_gateway_tracking_id ON payment_transactions (gateway_tracking_id);
CREATE INDEX ix_payment_transactions_listing_id ON payment_transactions (listing_id);
