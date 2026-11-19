# Backup and recovery runbook

Development only until ASUFC approves the host and data retention policy.

- Run `bash scripts/backup.sh /approved/private/backup-directory` from the repository root. Archive permissions are restricted by umask; the archive contains financial records and password hashes, so use encrypted storage, restricted operator access and an approved offsite copy. SHA-256 checks accidental corruption; it does not authenticate an archive against an attacker.
- Run `bash scripts/restore-check.sh PATH.dump` on a trusted host. It restores to a newly named disposable database, checks basic schema and record counts and removes the temporary database. It does not replace the live database. Only use trusted archives.
- For real disaster recovery, stop application writes, preserve the damaged database, restore into a fresh database on an authorized host using pg_restore with --exit-on-error, configure PGDATABASE to the restored target, verify financial reconciliation and compare records against known totals, rotate staff credentials, and obtain operator approval before reopening access. Never restore over the only existing copy.
- Session and login attempt rows are excluded from backup; the credential hash is included. Rotate credentials after a recovery. No real backups are uploaded into GitHub Actions.
- Proposed daily backup and periodic restore drill cadence requires ASUFC approval; no scheduled production backups have been activated.
