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
