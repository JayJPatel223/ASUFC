# Progress
Initial backend foundation: PostgreSQL schema, default program codes, funding confirmation, budget allocation, split purchase validation, transaction list and dashboard aggregates. Integer cents. Local-only development authentication. Unit tests authored; execution not yet verified.
Next: integration tests against PostgreSQL, proper session authentication, audit/correction lifecycle, React dashboard and forms, academic year rules, migrations, Excel and AI. No production deployment or real data.

Verification: 9 of 9 financial validation unit tests passed using Python pytest in an isolated environment. Git blob hashes of rules.py and test_rules.py matched the committed files. PostgreSQL/API integration and Docker startup were not tested because Docker and PostgreSQL were unavailable. No production readiness claim.

## Frontend milestone
Added React/TypeScript/Vite interface with local in-memory credentials, live API dashboard, funding and receipt confirmation forms, program budget allocations, split expense entry, searchable transaction history and academic-year/month/program filters. Basic CSS chosen instead of Tailwind/shadcn to minimize dependencies. No hardcoded balances. Frontend build and browser/API integration have not been verified in this milestone.

## Remaining work (priority order)
- Run dependency install, type check, build, browser tests and PostgreSQL integration tests; add CI.
- Production staff authentication, account handover, sessions, CSRF protections as applicable, HTTPS and deployment review.
- Full grant metadata and restrictions, configurable funding priorities, budget adjustments and custom program codes.
- Academic-year dates and validation, carry-forward; funding receipt history.
- Immutable audit trail, corrections/voids, receipt attachments and backups.
- Dashboard monthly charts, recent transactions, expiry thresholds, eligible funding recommendations.
- Reports, Excel export/import, duplicate detection and approved AI integration.

## Testing and allocation recommendation milestone
- Re-ran the 9 existing backend financial rule tests: 9 passed. Ran 6 frontend API and money utility tests using Node with mocked fetch: 6 passed. TypeScript compilation of the API utility module passed.
- Added 4 funding suggestion unit tests: 4 passed; total observed unit test results: 19 passed, 0 failed. Verified local tested suggestion source/test Git blob hashes match repository files (176f564a83327e1f0cf233a4ccc0d6ffa18d0ca4 and 702b8e0297a1f69d703595ba51a920e2852200ce).
- Added GitHub Actions workflow for full frontend build, frontend tests and PostgreSQL API integration tests using disposable test credentials. CI results not yet available via connector; integration tests authored but not executed locally. Direct Git clone/network dependencies and PostgreSQL/Docker were unavailable in execution environment. Browser rendering not verified.
- Added read-only POST /allocation-suggestions and purchase form integration. Supports a selected program, payment type, supplier, date, amount, academic year and optional preferred funding source. Proposed priority: preferred source, then earliest expiry, then stable budget ID. Only eligible existing budget allocations considered; shows shortfall if insufficient. Staff must review and explicitly save. Manual multi-program and mixed cash/credit allocations remain supported through existing purchase form. This is deterministic assistance, not AI. Priority policy and actual grant rules require stakeholder confirmation.
- Next: verify CI and resolve failures, implement comprehensive audit/corrections and secure staff sessions, add budget adjustments, expand dashboard analytics and reporting, then Excel and approved AI features. Not production-ready.

## Financial record integrity milestone
- Added additive schema changes: purchase_void, audit_event, active_allocation view. Original allocations remain in history; balance and recommendation queries exclude voided purchases.
- Added POST /transactions/{id}/void, PATCH /budgets/{id}, GET /audit. Changes require a reason for voids and budget adjustments; writes and audit entries share a transaction. Frontend includes audit log, void confirmation, budget adjustment and transaction status.
- Audit UI returns latest 500 events; pre-existing records are not backfilled. Staff identity uses the existing development credential. Audit log is application-level, not tamper-proof against DB administrators. Corrections are void plus separately recorded replacement, not atomic or explicitly linked yet.
- Reconstructed committed financial rules and suggestion modules and tests locally; git blob hashes matched, including updated test_rules.py cdcc4c0a9b06bd3b3407bc71beaf7bdf9161335b. Executed python -m pytest: 15 passed, zero failed, including two new regression tests (duplicate budget and cross-year rejection). Previous six frontend utility results were not rerun this round.
- Added PostgreSQL integration regression for voiding, balance restoration, duplicate void rejection, budget limits and audit events. Not executed: PostgreSQL, psycopg and Docker unavailable. Git clone failed DNS lookup. Connector returned no workflow runs or combined statuses; full UI build and integration remain unverified.
- Next: verify CI, add linked atomic correction, audit pagination and secure staff sessions, then reporting, Excel, academic-year rollover, receipt handling and approved AI. Do not use real data yet.
