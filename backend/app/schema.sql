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

CREATE TABLE IF NOT EXISTS purchase_correction (
 original_id bigint PRIMARY KEY REFERENCES purchase_void(purchase_id),
 replacement_id bigint UNIQUE NOT NULL REFERENCES purchase(id),
 CHECK(original_id <> replacement_id)
);
ALTER TABLE funding ADD COLUMN IF NOT EXISTS organization text NOT NULL DEFAULT '';
ALTER TABLE funding ADD COLUMN IF NOT EXISTS source_type text NOT NULL DEFAULT '';
ALTER TABLE funding ADD COLUMN IF NOT EXISTS recurring boolean NOT NULL DEFAULT false;
ALTER TABLE funding ADD COLUMN IF NOT EXISTS expected_date date;
ALTER TABLE funding ADD COLUMN IF NOT EXISTS notes text NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS funding_receipt (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 funding_id bigint NOT NULL REFERENCES funding(id),
 cents bigint NOT NULL CHECK(cents > 0),
 received_on date,
 recorded_at timestamptz NOT NULL DEFAULT now(),
 actor text NOT NULL
);
-- Legacy amounts have no known receipt date; retain that uncertainty.
INSERT INTO funding_receipt(funding_id,cents,actor)
 SELECT f.id,f.received_cents,'legacy opening balance' FROM funding f
 WHERE f.received_cents>0 AND NOT EXISTS (SELECT 1 FROM funding_receipt r WHERE r.funding_id=f.id);

CREATE TABLE IF NOT EXISTS academic_period (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 academic_year text UNIQUE NOT NULL,
 starts_on date NOT NULL,
 ends_on date NOT NULL,
 CHECK(starts_on <= ends_on)
);
CREATE TABLE IF NOT EXISTS semester (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 period_id bigint NOT NULL REFERENCES academic_period(id),
 name text NOT NULL,
 starts_on date NOT NULL,
 ends_on date NOT NULL,
 CHECK(starts_on <= ends_on),
 UNIQUE(period_id,name)
);

ALTER TABLE funding ADD COLUMN IF NOT EXISTS carry_eligible boolean NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS funding_transfer (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 source_id bigint NOT NULL REFERENCES funding(id),
 destination_id bigint UNIQUE NOT NULL REFERENCES funding(id),
 cents bigint NOT NULL CHECK(cents>0),
 reason text NOT NULL CHECK(length(trim(reason))>0),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(source_id<>destination_id)
);
CREATE OR REPLACE VIEW funding_capacity AS
 SELECT f.*, COALESCE(i.cents,0) AS carried_in_cents, COALESCE(o.cents,0) AS carried_out_cents,
 f.received_cents + COALESCE(i.cents,0)-COALESCE(o.cents,0) AS capacity_cents
 FROM funding f
 LEFT JOIN (SELECT destination_id,sum(cents) AS cents FROM funding_transfer GROUP BY destination_id) i ON i.destination_id=f.id
 LEFT JOIN (SELECT source_id,sum(cents) AS cents FROM funding_transfer GROUP BY source_id) o ON o.source_id=f.id;

ALTER TABLE budget DROP CONSTRAINT IF EXISTS budget_cents_check;
ALTER TABLE budget ADD CONSTRAINT budget_cents_check CHECK(cents >= 0);

CREATE TABLE IF NOT EXISTS import_entry (
 external_id text PRIMARY KEY,
 purchase_id bigint UNIQUE NOT NULL REFERENCES purchase(id)
);

CREATE TABLE IF NOT EXISTS funding_transfer_void (
 transfer_id bigint PRIMARY KEY REFERENCES funding_transfer(id),
 reason text NOT NULL CHECK(length(trim(reason))>0),
 actor text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE VIEW active_funding_transfer AS
 SELECT t.* FROM funding_transfer t LEFT JOIN funding_transfer_void v ON v.transfer_id=t.id WHERE v.transfer_id IS NULL;
CREATE OR REPLACE VIEW funding_capacity AS
 SELECT f.*, COALESCE(i.cents,0) AS carried_in_cents, COALESCE(o.cents,0) AS carried_out_cents,
 f.received_cents + COALESCE(i.cents,0)-COALESCE(o.cents,0) AS capacity_cents
 FROM funding f
 LEFT JOIN (SELECT destination_id,sum(cents) AS cents FROM active_funding_transfer GROUP BY destination_id) i ON i.destination_id=f.id
 LEFT JOIN (SELECT source_id,sum(cents) AS cents FROM active_funding_transfer GROUP BY source_id) o ON o.source_id=f.id;

CREATE TABLE IF NOT EXISTS funding_purchase_type (
 funding_id bigint PRIMARY KEY REFERENCES funding(id),
 purchase_type text NOT NULL CHECK(length(trim(purchase_type))>0)
);

CREATE TABLE IF NOT EXISTS staff_session (
 token_hash text PRIMARY KEY,
 username text NOT NULL,
 expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS staff_login_attempt (
 attempted_at timestamptz NOT NULL DEFAULT now()
);
