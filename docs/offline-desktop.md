# Offline staff desktop app

The desktop build is intended for one designated staff computer. It bundles the React interface, Python staff API and PostgreSQL 16. The desktop window starts the API and database automatically, and both listen on loopback. Staff can use the application after installation with the computer disconnected from the internet. The developer build downloads platform dependencies before packaging.

First launch asks staff to choose a local password. The established ledger, credential hash and audit history remain in the current operating-system user's ASUFC Finance application data folder when the app closes. Running the same installed app as another operating-system user creates a separate ledger. Use a single operating-system profile for the designated computer.

## Candidate builds

The Offline staff runtime workflow builds and tests Windows x64, Linux x64, macOS Apple Silicon and macOS Intel. It exercises the packaged backend with its own PostgreSQL engine, including account setup, recording a purchase, XLSX export and relaunch. It also checks first launch, sign-in and reopening through the desktop window before creating test installers.

The installer files are development candidates for use with fictional data. Release work still includes signing, installation on a clean offline computer, upgrade testing, reviewing the bundled native libraries, and creating a staff-managed offline backup and restore flow. File-based receipt storage and the remaining staff application features are tracked in the roadmap.

## Development build

Build the staff frontend with `npm ci` and `npm run build` in `frontend/`. In a Python 3.12 virtual environment, install the backend development requirements and PyInstaller. From the repository root, run `python scripts/stage_desktop_runtime.py --output desktop/runtime` in a clean staging directory. Use `npm ci` in `desktop/`, followed by `npm run package` to produce the candidate for the current computer. The automated workflow defines the package checks for each supported target.

Current verification uses fictional data only. Preserve the application data folder and its database password file together when testing machine migration. Copying a running PostgreSQL data directory does not provide a verified backup.
