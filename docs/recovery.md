# Backup and recovery runbook

Development only until ASUFC approves the host and data retention policy.

- Run `bash scripts/backup.sh /approved/private/backup-directory` from the repository root. Archive permissions are restricted by umask; the archive contains financial records and password hashes, so use encrypted storage, restricted operator access and an approved offsite copy. SHA-256 checks accidental corruption; it does not authenticate an archive against an attacker.
- Run `bash scripts/restore-check.sh PATH.dump` on a trusted host. It restores to a newly named disposable database, checks basic schema and record counts and removes the temporary database. It does not replace the live database. Only use trusted archives.
- For real disaster recovery, stop application writes, preserve the damaged database, restore into a fresh database on an authorized host using pg_restore with --exit-on-error, configure PGDATABASE to the restored target, verify financial reconciliation and compare records against known totals, rotate staff credentials, and obtain operator approval before reopening access. Never restore over the only existing copy.
- Session and login attempt rows are excluded from backup; the credential hash is included. Rotate credentials after a recovery. No real backups are uploaded into GitHub Actions.
- Proposed daily backup and periodic restore drill cadence requires ASUFC approval; no scheduled production backups have been activated.

## Encrypted backup option
Install age on the authorized host. Generate an identity offline using `age-keygen -o private.agekey`; store it separately from backups. Set ASUFC_BACKUP_RECIPIENT to its public age recipient. Run `bash scripts/backup-encrypted.sh /approved/private/directory`. No plaintext archive is written by this script. For a drill set ASUFC_BACKUP_IDENTITY to the approved private identity path and run `bash scripts/restore-encrypted-check.sh PATH.dump.age`. Use trusted archives and test recovery before relying on a backup. The systemd service/timer templates in deploy/ are proposed, inactive configuration: adjust paths, account, Docker access, and approved schedule before installation. Keep the private decryption identity off the backup host whenever feasible. Retention and offsite storage require institutional approval.

Backup monitoring: `bash scripts/check-backup.sh /approved/private/directory 30` checks freshness, completeness and checksum. Inactive systemd templates log failures to the host journal; the operator must connect journal alerts to an approved monitoring destination. No external notifications or scheduled production jobs are activated.
