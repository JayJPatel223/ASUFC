# ASUFC Financial Management
Development prototype. Use fictional data only; never upload real records or secrets.

## Local setup
1. Install Docker Compose and Node.js 20 or newer.
2. Copy .env.example to .env and replace both passwords with random values.
3. Run `docker compose up --build` from the repository root.
4. In another terminal run `cd frontend`, `npm install`, then `npm run dev`.
5. Open the local Vite URL printed in the terminal (usually http://127.0.0.1:5173). Sign in with configured STAFF_USER and STAFF_PASSWORD.

The Vite development proxy connects to the API at 127.0.0.1:8000. API documentation is at http://127.0.0.1:8000/docs. Do not expose this development configuration publicly.

Backend unit tests: `docker compose run --rm api python -m pytest`.
Frontend type check and build: `cd frontend && npm run build`.

See docs/architecture.md and PROGRESS.md for limitations. No production readiness claim.
