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

## Spending reports milestone
- Added allocation-level reporting service, GET /reports/spending and React Reports page. Filters: academic year, date interval, program, exact case-insensitive supplier, funding ID. Cash and purchasing credits are separate; voided purchases excluded; count distinct purchases rather than allocations. Filtered totals reflect matching allocations only.
- Four new reporting unit tests executed locally: 4 passed in 0.06s. Tested Git blob hashes matched repository (reporting.py a4726c8965a2c1ab412f6737b705f2683d64c745; test_reporting.py 0a0e57bfbc479d6903132c329af5dc4fd8c15a52). Added PostgreSQL reporting regression test but not executed. Cumulative historical unit-test count 25; not a single full-suite run.
- Reports currently use tables and summary cards, not charts. Semester configuration, zero-spend month filling, supplier normalization, exports, and secure production sessions remain outstanding. Git clone still fails DNS; PostgreSQL/Docker and full frontend integration not verified. No real financial data.

## Finance-first milestone
- Added spending Excel export with six sheets, shared report filters, purchase type filter and monthly cash/credit chart. Text cells forced to string to prevent formula execution. Export is allocation-level, not a full ledger backup.
- Executed two Excel unit tests locally with openpyxl 3.1.5: 2 passed in 0.18s. Git blob hashes matched export.py c22be31e84401fa2773b8de59535b59ff2a60d47, reporting.py a4726c8965a2c1ab412f6737b705f2683d64c745 and test_export.py abcc2b5850212ee9950d65f4ab2f9dcb0a31cd8b. No full-suite rerun. Git DNS access remains blocked.
- Finance acceptance gates outstanding: full PostgreSQL and frontend build/browser tests; atomic linked corrections; academic-year/semester configuration and carry-forward; full grant restrictions and receipt history; funding and budget balance report/export; Excel migration with duplicate prevention; financial reconciliation, concurrency and security checks. Do not claim 100% until verified. Defer AI and unrelated enhancements.

## CI incident resolution — 2026-11-19
- Failed run [44553037436](https://github.com/JayJPatel223/ASUFC/actions/runs/44553037436), backend job 135661566452: pytest collection failed with ModuleNotFoundError: No module named 'openpyxl' because Excel tests landed before the dependency manifest update.
- Fixed by existing commit 834c239729ce9c80b028eda247711d5fe6a55e07 adding openpyxl>=3.1,<4. Verified subsequent runs; latest tested commit 40b7254b1f5f3c193e427f4d5343aba860f5cad2 [CI run 44553207681](https://github.com/JayJPatel223/ASUFC/actions/runs/44553207681) succeeded in both jobs. Backend log: 24 passed, 1 warning in 0.76s, including three real PostgreSQL integration tests. Frontend log: TypeScript/Vite build succeeded; 6 tests passed, zero failed/skipped. Total 30 passing tests in this single CI run. Browser end-to-end testing, concurrent writes, full financial acceptance and production security still pending.
- Nonblocking warnings: Starlette TestClient httpx deprecation and GitHub Actions runtime deprecation. Review dependency compatibility separately; not the cause of the failed run.
- Process improvement: commit dependency manifests, implementation and corresponding tests together in one atomic Git commit, and verify the current CI job logs before declaring a milestone tested. Earlier local integration limitations do not negate the successful CI tests above.

## Linked corrections and grant receipts
- Atomic correction endpoint, rollback on invalid replacement, original/replacement linkage and receipt history. Added grant organization, classification, recurrence, expected date, notes. Frontend correction and receipt views added. CI verification pending for this commit; further restriction and year management work remains.

## Academic period configuration
Added configurable consecutive academic years and non-overlapping semesters; purchase dates validated when a year has been configured. Legacy unconfigured year buckets still supported until dates are confirmed. No assumed Acadia dates seeded. New integration test added; CI pending. Carry-forward remains outstanding.

Academic period configuration UI, year selector and semester report presets added. CI pending. Year configuration is creation-only; edits and funding rollover require separate safeguarded workflows.

## Funding carry-forward backend
Separate transfer records preserve new receipts vs transferred balances. Only explicitly permitted grants can transfer unallocated capacity to the configured next academic year; expiry and existing restrictions preserved, no new receipt, destination eligibility defaults false. Zero-spend budgets can be reduced to zero. Transfer timing policy (pre-year planning allowed) needs stakeholder confirmation. Frontend and CI verification pending.

Carry-forward permission and transfer forms, transfer history, separate carried-in/out dashboard metrics, and capacity-based balances connected to frontend. CI pending. Transfers are not reversible through the UI yet; stakeholder timing and permissions require confirmation.

## Internal reconciliation and balance reports
Added independent raw-ledger calculations under a consistent read-only PostgreSQL snapshot; detects mismatched receipts and purchase allocations, cross-year purchases, overspent budgets/funding, overallocations, transfer year/type mismatch. New Reconciliation page with source and budget balances. No external bank reconciliation or automatic repair. Added three unit tests and one PostgreSQL integration regression with deliberately inconsistent disposable test data. CI pending.

Added reconciliation workbook export with funding, budget and issue worksheets, formula-safe text and authenticated download. Added workbook and download regression tests. Internal reconciliation is not external bank verification. CI pending.

## Excel migration and custom programs
Added bounded XLSX parsing, explicit seven-column mapping, formula rejection, transaction-path preview with rollback, atomic import and stable external ID deduplication. Conservative date/supplier/amount collision blocks potential duplicate imports. Single-budget rows only; split historical purchases require manual entry. Custom program creation added. Actual ASUFC workbook not supplied; mapping and historical expiry policy require confirmation. CI pending.

Added audited transfer reversals (blocked if destination capacity would fall below allocations/spending), active-transfer accounting and frontend reversal form. Added PostgreSQL reversal and concurrent overspending regressions. CI pending.
