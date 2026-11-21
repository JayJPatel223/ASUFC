# Offline staff desktop app

The desktop build is intended for one designated staff computer. It bundles the React interface, Python staff API and PostgreSQL 16. The desktop window starts the API and database automatically, and both listen on loopback. Staff can use the application after installation with the computer disconnected from the internet. The developer build downloads platform dependencies before packaging.

Version 0.4 opens directly to **Overview**, including on first launch. Keep the designated operating-system account locked when the workstation is unattended. The ledger and audit history stay in the existing ASUFC Finance application data folder for that profile. Running the app under another operating-system profile uses a separate ledger.

## Candidate builds

The Offline staff runtime workflow builds and tests Windows x64, Linux x64, macOS Apple Silicon and macOS Intel. It checks direct launch, local API access, recording a purchase, XLSX export, encrypted recovery and reopening saved records. It also runs the staff UI and receipt-photo flow through the desktop window before creating test installers.

Each workflow artifact contains the installer and its SHA-256 checksum. The workflow installs the NSIS build on Windows, opens and copies the app from the macOS disk image, and extracts the Linux AppImage. It runs financial and recovery checks using the runtime shipped in those files. CI uses disposable ledgers and fictional data.

## Handover and recovery

Follow the [staff handbook](staff-handbook.md) for setup, purchase review and backup. The portable backup contains the financial ledger, pending purchases, receipts and audit history. Open **Account → Restore an encrypted backup** in an empty ledger. Version 0.3 files use their original backup passphrase. Continue using the previous ledger until the recovered purchase totals and receipt history match.

Before handing over the app, install it with networking disabled on the designated computer. On a disposable profile, open the app, record a purchase, attach a receipt, generate a report, close and reopen the app, and verify backup recovery in another fresh profile. Before an upgrade, save a backup and retain the previous installer. Install the new version with the app closed, then compare the balances and latest records in the same profile. Use version 0.4 or a compatible newer build for backups made from a new 0.4 ledger.

## Notes for maintainers

- [desktop/main.cjs](../desktop/main.cjs) starts the runtime and gives it a random credential over its private input pipe. It puts the credential in a session-only HttpOnly cookie in the desktop window. [backend/app/desktop.py](../backend/app/desktop.py) uses it to authorize the loopback API and requires the application request header for writes. The hosted staff workspace uses its password-based login.
- [frontend/src/desktop-backup.tsx](../frontend/src/desktop-backup.tsx) provides the backup and recovery controls. The desktop launcher selects the backup through the operating-system file picker and sends the path directly to the runtime. Restore checks the empty-ledger requirement under a database lock and rolls back if the file is damaged or the passphrase is wrong.
- [scripts/verify_desktop_runtime.py](../scripts/verify_desktop_runtime.py) tests the runtime. Its optional `--legacy-runtime` argument takes the `resources/runtime` directory from an extracted 0.3 installer to test an in-place ledger upgrade and a backup made by 0.3. Use fictional data for your development checks.

Windows and macOS unsigned workflow artifacts are development candidates. An authorized repository maintainer can run **Offline staff runtime** on `main` with **Sign Windows and macOS packages** enabled after institutional signing credentials are configured. The workflow accepts a macOS Developer ID Application certificate through `DESKTOP_MAC_CSC_LINK` and `DESKTOP_MAC_CSC_KEY_PASSWORD`, and App Store Connect notarization credentials through `DESKTOP_APPLE_API_KEY_BASE64`, `DESKTOP_APPLE_API_KEY_ID` and `DESKTOP_APPLE_API_ISSUER`. The Windows PFX integration uses `DESKTOP_WIN_CSC_LINK` and `DESKTOP_WIN_CSC_KEY_PASSWORD`. It checks the installed signature or app notarization before uploading signed artifacts. Hardware-backed or managed Windows signing requires the corresponding institutional setup.

## Development build

Build the staff frontend with `npm ci` and `npm run build` in `frontend/`. In a Python 3.12 virtual environment, install the backend development requirements and PyInstaller. From the repository root, run `python scripts/stage_desktop_runtime.py --output desktop/runtime` in a clean staging directory. Use `npm ci` in `desktop/`, followed by `npm run package` to produce the candidate for the current computer. The automated workflow defines the package checks for each supported target.

Use fictional data for development and testing. Use the in-app backup to move records between computers. The [academic handover](university-handover.md) documents scope, security, diagrams and verification.
