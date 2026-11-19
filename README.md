# ASUFC Financial Management
Development prototype. Use fictional data only; never upload real records or secrets.

## Local setup
1. Install Docker Compose and Node.js 22.12+ (or a supported Node 20.19+ release).
2. Copy .env.example to .env and replace both passwords with random values.
3. Run `docker compose up --build` from the repository root.
4. In another terminal run `cd frontend`, `npm install`, then `npm run dev`.
5. Open the local Vite URL printed in the terminal (usually http://127.0.0.1:5173). Sign in with configured STAFF_USER and STAFF_PASSWORD.

The Vite development proxy connects to the API at 127.0.0.1:8000. Public API documentation is disabled. Do not expose this development configuration publicly.

Backend unit tests: `docker compose run --rm api python -m pytest`.
Frontend type check and build: `cd frontend && npm run build`.

See docs/architecture.md and PROGRESS.md for limitations. No production readiness claim.

## Staff credentials
STAFF_PASSWORD is a one-time bootstrap password (minimum 16 characters); subsequent changes are stored as salted scrypt hashes. Change password in Account; all sessions are revoked. Trusted host operator recovery: `docker compose exec api python -m app.reset_password`. Password is entered interactively, never as a shell argument. Keep STAFF_USER stable; changing it is not an account handover procedure.

## HTTPS deployment candidate
Use Docker Compose 2.24.4+ on an authorized host, configure ASUFC_DOMAIN to its actual DNS hostname, set unique secrets, and run `docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d`. The Caddy gateway serves the built frontend and same-origin API, obtains certificates when DNS and ports are configured, and enables secure cookies and security headers. Do not expose the local development configuration. Deployment must be validated with the actual domain and institutional approval; this is not a live deployment.

Browser checks: `cd frontend && npx playwright install chromium && npm run test:e2e` with local API running and STAFF_USER/STAFF_PASSWORD exported; use disposable data only.

## Backup and recovery
See [recovery runbook](docs/recovery.md). Create an archive with `bash scripts/backup.sh` and validate it using `bash scripts/restore-check.sh PATH.dump`. Use approved encrypted storage; never commit archives.

## Public GitHub Pages demo
Set Settings > Pages > Source to GitHub Actions. The dedicated Pages workflow builds with `npm run build:pages`, tests the compiled demo and publishes only frontend/dist. The public demo uses fictional in-memory records and a single Enter public demo button; no real login, API, database, persistence or file processing. Refresh resets all records. Core funding, budgets, purchase, void and reports can be exercised; server-only operations are explicitly unavailable. Never enter real data. Normal local and production builds continue to use the authenticated backend.
