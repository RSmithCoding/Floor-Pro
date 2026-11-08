# Data Model: Backup and Restore

**Feature**: 002-backup-restore | **Date**: 2026-11-08

This feature adds **no database tables and no Alembic migration**. Everything it stores
describes this computer's backup setup, so it lives in files in the data folder, outside
`floorpro.db`. Otherwise a restore would overwrite it ([research §5](research.md#5-backup-preferences-live-outside-the-database)).

```text
<data dir>/                      macOS: ~/Library/Application Support/FloorPro
├── floorpro.db                  shop data (unchanged by this feature, except by restore)
├── secret.key                   feature 001: cookie/token signing
├── backup-key.json              NEW: derived backup key (§2)
├── backup-settings.json         NEW: backup preferences and last results (§3)
├── backups/                     "This computer" location: .fpbackup files (+ legacy pre-upgrade .db)
├── tmp/                         NEW: snapshots, staged restores, uploads (cleared at startup)
├── damaged/                     NEW: unreadable databases moved aside by recovery (never deleted)
└── logs/
<chosen folder>/                 optional, chosen by the user: .fpbackup files
```

## 1. Backup (a file)

One `.fpbackup` file per backup. The byte layout and header are specified in
[contracts/backup-file.md](contracts/backup-file.md). In code it is a `BackupInfo` value read
from the header plus file system facts:

| Field | Type | Source | Rules |
|-------|------|--------|-------|
| `location` | `"local"` \| `"folder"` | where it was found | `local` = `<data dir>/backups`, `folder` = chosen folder. `before_restore` and `before_upgrade` are always `local` |
| `filename` | str | file name | must match `^FloorPro-backup-\d{4}-\d{2}-\d{2}-\d{6}-(manual\|automatic\|before-restore\|before-upgrade)(-\d+)?\.fpbackup$`, or the legacy `^floorpro-\d{8}T\d{12}Z-pre-[0-9a-z_]+\.db$` |
| `kind` | `BackupKind` | header `kind` | `manual`, `automatic`, `before_restore`, `before_upgrade` |
| `created_at` | aware datetime (UTC) | header `created_at` | shown in local time |
| `app_version` | str | header | FloorPro version that made it |
| `schema_revision` | str \| None | header | Alembic revision; `None` = empty database at `base` |
| `contents` | dict[str, int] | header `contents` | at least `{"customers": n}` |
| `size_bytes` | int | file size | shown as "2.4 MB" |
| `protected` | bool | file type | `False` only for legacy plain `.db` pre-upgrade copies. These are listed only; they're converted to protected backups when the password is first set. In recovery mode they can be restored |
| `key_id` | bytes \| None | header | compared to this computer's key id |
| `needs_password` | bool | derived | `protected and key_id != current key_id` |

**`BackupKind` labels**: Manual · Automatic · Before restore · Before upgrade.

**Rules**:
- **Identity**: a backup is identified by `(location, filename)`. A path built from those must
  resolve inside the location folder.
- **Unreadable headers**: a file whose header can't be read is listed as "Damaged or not a
  FloorPro backup". It can be deleted, but never restored.
- **Most recent successful**: the newest `created_at` across both locations, of any kind, so
  a newer automatic or Before restore backup lets an older manual one be deleted. It can't be
  deleted (FR-021).
- **Retention** (applied after each automatic backup, FR-018):
  - Automatic: keep the newest 14 across both locations.
  - Before upgrade: keep the newest 10 (local only).
  - Manual and Before restore: never pruned.

**Lifecycle**:

```text
(snapshot) → writing (.partial) → complete (.fpbackup)
                    └── error → partial removed, failure recorded
complete → deleted (user, after confirm; or retention)
```

## 2. Backup key — `backup-key.json`

Exists only after a backup password has been set. "Password set" means this file exists and
is valid.

| Field | Type | Rules |
|-------|------|-------|
| `version` | int | `1` |
| `kdf` | object | `{"name": "scrypt", "n": 131072, "r": 8, "p": 1, "salt": "<base64, 16 bytes>"}` |
| `key` | base64 str | 32-byte key derived from the password; never the password |
| `key_id` | base64 str | 16 bytes, `HMAC-SHA256(key, b"floorpro-backup-key-id")[:16]` |
| `set_at` | ISO-8601 UTC str | when the password was set or last changed |

**Rules**:
- Written atomically.
- Replaced as a whole on password change, never edited in place.
- Never copied into a backup or a chosen folder.
- If the file is missing or invalid, the app treats it as "no password set". It logs a warning,
  and the Backups screen asks for a password.

## 3. Backup preferences — `backup-settings.json`

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `version` | int | `1` | |
| `auto_enabled` | bool | `true` | FR-019 |
| `folder` | str \| null | `null` | chosen backup folder (absolute path); `null` = this computer |
| `last_success_at` | ISO UTC \| null | `null` | last backup of any kind that completed (not Before upgrade) |
| `last_auto_date` | `YYYY-MM-DD` (local) \| null | `null` | local date of the last automatic attempt; used for "once a day" |
| `last_auto_ok` | bool \| null | `null` | result of that attempt |
| `last_auto_error` | str \| null | `null` | plain-English reason if it failed |
| `last_fallback_at` | ISO UTC \| null | `null` | last time an automatic backup fell back to this computer (FR-024) |

**Rules**:
- Written atomically.
- Unknown fields are ignored.
- A missing or invalid file means the defaults. A new file is written on the next change.
- **Effect of a successful automatic backup to the chosen folder**: it clears
  `last_fallback_at`, so the "couldn't be reached" warning goes away once the drive is back.

## 4. Dashboard backup status (derived, not stored)

`domain/backups.backup_status(prefs, key_set, now) -> list[BackupWarning]`. Checks run in
this order and every match is returned (each has a `message` and `level`):

| Condition | Message |
|-----------|---------|
| not `key_set` | "Set a backup password to start backing up." |
| `last_auto_ok is False` | "The last automatic backup failed: {last_auto_error}" |
| `last_fallback_at` set | "Your backup folder couldn't be reached, so backups were saved on this computer." |
| not `auto_enabled` | "Automatic backups are off." |
| `last_success_at` is null or older than 7 days | "No backup in the last 7 days." / "No backups yet." |

An empty list means the dashboard shows a quiet "Last backup: today at 09:02" line instead of
a warning.

## 5. Recovery state (in memory)

`app.state.recovery: RecoveryInfo | None`:

| Field | Type | Meaning |
|-------|------|---------|
| `reason` | str | plain-English explanation shown on `/recovery` |
| `detail` | str | technical error, written to the log only |
| `detected_at` | datetime | |

Recovery mode is set during startup when opening, checking or migrating `floorpro.db` fails
([research §13](research.md#13-startup-recovery-fr-025)). It's cleared after a successful
restore or "Start with no data".

## 6. Validation rules summary

| Input | Rule | Message |
|-------|------|---------|
| New password | ≥ 10 characters after NFC, not only spaces | "Use at least 10 characters." |
| New password | ≤ 1,024 characters | "Use at most 1,024 characters." |
| Confirm password | equals new password | "The two passwords don't match." |
| Current password (change) | required | "Enter your current backup password." |
| Current password (change) | key id matches | "That isn't the current backup password." |
| Restore confirmation | exactly `RESTORE` (spaces trimmed, any case) | "Type RESTORE to confirm." |
| Backup password (restore) | required when `needs_password` | "Enter the password this backup was made with." |
| Backup password (restore) | derives the header's key id | "That password doesn't open this backup." |
| Folder (browser mode) | absolute path to an existing, writable folder | "Choose a folder FloorPro can save to." |
| Start with no data (recovery) | exactly `START AGAIN` | "Type START AGAIN to confirm." |
