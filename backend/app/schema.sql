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
