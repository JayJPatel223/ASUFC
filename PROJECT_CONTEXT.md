# ASUFC Finance project context

The Acadia Students' Union Food Cupboard partnered with the COMP 2663 Software Engineering 1 team to replace manual Excel spending and funding tracking. Staff must be able to trace purchases to eligible budgets and distinguish confirmed cash, purchasing credits and expected funding. The requirements cover the four existing program codes and custom programs, split allocations, purchase review and corrections, expiry, audited budget and funding changes, historical academic years and reporting.

React and Vite provide the interface. FastAPI authenticates staff, applies financial and eligibility rules and reads and writes a PostgreSQL ledger through Psycopg. Budget balances represent allocations to a program and funding source. A confirmed purchase spends from one or more budgets. Voiding preserves the recorded purchase and restores its available balances. Internal reconciliation checks the ledger. Bank or card settlement requires separate evidence.

The staff application implements funding receipts, separate cash and credit accounting, audited financial mutations and funding expiry edits, allocation suggestions, duplicate review, purchasing restrictions, program budgets, reports, bounded XLSX import and export, editable academic periods and semesters, authorized carry-forward and reversals. The Caddy Compose configuration supports a private HTTPS gateway. The recovery runbook covers encrypted backups and disposable restore checks. Staff access currently uses one designated account with server-side sessions and an operator recovery procedure.

The [public demonstration](https://jayjpatel223.github.io/ASUFC/) uses a separate Vite build and an in-memory mock transport. Reloading resets the fictional records. The demo supports core spending workflows. Server features such as Excel processing, credential management and actual grants are handled by the staff application.

Institutional access, funding rules, formal reporting cutoffs, production hosting and encryption key custody require confirmed stakeholder decisions. The code models one eligible program, supplier and purchase type per funding source. Complex grant terms may also require staff review. Secure transaction receipt files and an AI provider are future work. Keep stakeholder records private and use fictional fixtures in development.

See [architecture](docs/architecture.md), [recovery](docs/recovery.md), [security review](docs/security-review.md), [roadmap](ROADMAP.md) and [progress](PROGRESS.md).
