CREATE TABLE IF NOT EXISTS program (
 code text PRIMARY KEY, name text NOT NULL
);
INSERT INTO program VALUES ('ASUFCGR','General Restocks'),('ASUFCFSBP','Foodsharing Breakfast Program'),('ASUFCE&W','Events & Workshops'),('ASUFCSIR','Specialty Item Restocks') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS funding (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text NOT NULL, academic_year text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('cash','credit')),
 expected_cents bigint NOT NULL CHECK(expected_cents >= 0),
 received_cents bigint NOT NULL CHECK(received_cents >= 0 AND received_cents <= expected_cents),
 expiry date, eligible_program text REFERENCES program(code), eligible_supplier text
);
CREATE TABLE IF NOT EXISTS budget (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 funding_id bigint NOT NULL REFERENCES funding(id),
 program_code text NOT NULL REFERENCES program(code),
 cents bigint NOT NULL CHECK(cents > 0), UNIQUE(funding_id,program_code)
);
CREATE TABLE IF NOT EXISTS purchase (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 purchase_date date NOT NULL, supplier text NOT NULL,
 purchase_type text NOT NULL, description text NOT NULL,
 cents bigint NOT NULL CHECK(cents > 0), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS allocation (
 purchase_id bigint REFERENCES purchase(id), budget_id bigint REFERENCES budget(id),
 cents bigint NOT NULL CHECK(cents > 0), PRIMARY KEY(purchase_id,budget_id)
);

-- Additive migration for existing development databases.
CREATE TABLE IF NOT EXISTS purchase_void (
 purchase_id bigint PRIMARY KEY REFERENCES purchase(id),
 reason text NOT NULL CHECK(length(trim(reason)) > 0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_event (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor text NOT NULL,
 action text NOT NULL,
 entity text NOT NULL,
 entity_id bigint NOT NULL,
 details jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_event_entity_idx ON audit_event(entity,entity_id);
CREATE OR REPLACE VIEW active_allocation AS
 SELECT a.* FROM allocation a LEFT JOIN purchase_void v ON v.purchase_id=a.purchase_id
 WHERE v.purchase_id IS NULL;
