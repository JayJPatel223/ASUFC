# Offline staff desktop app

The desktop build is intended for one designated staff computer. It bundles the React interface, Python staff API and PostgreSQL 16. The desktop window starts the API and database automatically, and both listen on loopback. Staff can use the application after installation with the computer disconnected from the internet. The developer build downloads platform dependencies before packaging.

First launch asks staff to choose a local password. The established ledger, credential hash and audit history remain in the current operating-system user's ASUFC Finance application data folder when the app closes. Running the same installed app as another operating-system user creates a separate ledger. Use a single operating-system profile for the designated computer.

## Candidate builds

The Offline staff runtime workflow builds and tests Windows x64, Linux x64, macOS Apple Silicon and macOS Intel. It exercises the packaged backend with its own PostgreSQL engine, including account setup, recording a purchase, XLSX export and relaunch. It also checks first launch, sign-in and reopening through the desktop window before creating test installers.

Each workflow artifact contains the installer and its SHA-256 checksum. The workflow installs the NSIS build on Windows, opens and copies the app from the macOS disk image, and extracts the Linux AppImage. It runs financial and recovery checks using the runtime shipped in those files. CI uses disposable ledgers and fictional data.

## Handover and recovery

Follow the [staff handbook](staff-handbook.md) for setup, purchase review and backup. The portable backup contains the financial ledger, pending purchases, receipt files, audit trail and staff credential hash. Restore it from first launch in a fresh operating-system profile. Continue using the previous ledger until the recovered purchase totals and receipt history match.

Before handing over the app, install it with networking disabled on the designated computer. On a disposable profile, set up staff access, record a purchase, attach a receipt, generate a report, close and reopen the app, and verify backup recovery in another fresh profile. Before an upgrade, save a backup and retain the previous installer. Install the new version with the app closed, then compare the balances and latest records in the same profile. If recovery is needed, use a fresh profile with a verified compatible backup.

Windows and macOS unsigned workflow artifacts are development candidates. An authorized repository maintainer can run **Offline staff runtime** on `main` with **Sign Windows and macOS packages** enabled after institutional signing credentials are configured. The workflow accepts a macOS Developer ID Application certificate through `DESKTOP_MAC_CSC_LINK` and `DESKTOP_MAC_CSC_KEY_PASSWORD`, and App Store Connect notarization credentials through `DESKTOP_APPLE_API_KEY_BASE64`, `DESKTOP_APPLE_API_KEY_ID` and `DESKTOP_APPLE_API_ISSUER`. The Windows PFX integration uses `DESKTOP_WIN_CSC_LINK` and `DESKTOP_WIN_CSC_KEY_PASSWORD`. It checks the installed signature or app notarization before uploading signed artifacts. Hardware-backed or managed Windows signing requires the corresponding institutional setup.

## Development build

Build the staff frontend with `npm ci` and `npm run build` in `frontend/`. In a Python 3.12 virtual environment, install the backend development requirements and PyInstaller. From the repository root, run `python scripts/stage_desktop_runtime.py --output desktop/runtime` in a clean staging directory. Use `npm ci` in `desktop/`, followed by `npm run package` to produce the candidate for the current computer. The automated workflow defines the package checks for each supported target.

Use fictional data for development and testing. Use the in-app backup to move records between computers. The [academic handover](university-handover.md) documents scope, security, diagrams and verification.
