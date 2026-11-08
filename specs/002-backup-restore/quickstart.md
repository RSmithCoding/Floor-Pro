# Quickstart & Validation: Backup and Restore

**Feature**: 002-backup-restore | **Date**: 2026-11-08

This guide proves the feature works end to end. Setup and running are as in
[feature 001's quickstart](../001-settings-customer-records/quickstart.md). Details live in
[data-model.md](data-model.md), [contracts/routes.md](contracts/routes.md) and
[contracts/backup-file.md](contracts/backup-file.md).

## Automated checks (same as CI)

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest                      # everything, including the slow 10,000-customer tests
uv run pytest -m "not slow"        # quick run
```

These cover:
- every route in the contract
- the file format, tampering, wrong passwords and damaged files
- restore exactness and fault injection (SC-003, SC-004)
- retention, the dashboard card and recovery mode
- the committed cross-platform fixture (SC-006), which runs on both macOS and Windows CI

## Manual walkthrough (desktop window)

To practise with throwaway data, start with a temporary data folder:

```bash
FLOORPRO_DATA_DIR=./dev-data uv run python -m floorpro
```

### A. Password first (US5)
1. Open **Backups** from the main navigation. Only the "Set a backup password" form is shown,
   with the warning that a forgotten password can't be recovered.
2. **Short password**: enter a 9-character password → "Use at least 10 characters."
3. **Mismatch**: enter two different passwords → "The two passwords don't match."
4. **Set it**: enter a valid password twice. Expect the toast "Backup password set".
   Within a few seconds an **Automatic** backup appears in the list.
5. **Dashboard**: with automatic backups on, the dashboard shows "Last backup: today at …"
   and no warning.

### B. Back up now (US1)
1. Add two customers.
2. Press **Back up now**. Expect "Backup made · N customers", and a **Manual** entry at the
   top with the date, size and customer count.
3. **Privacy**: open the `.fpbackup` file in a text editor. No customer names, phones or
   emails can be found (SC-008).

### C. Restore (US2)
1. Erase or edit a customer, then choose **Restore** on the manual backup.
2. **Confirm dialog**: the dialog shows the date, type and customer count, plus the warning.
   **Restore** with the wrong word gives "Type RESTORE to confirm."
3. **Restore**: type `RESTORE`. The app returns to the dashboard with "Restored the backup
   from …", and the customer is back. No restart is needed.
4. **Undo**: a **Before restore** backup is now in the list. Restoring it undoes step 3.
5. **Time it** (SC-005): time a first-time restore from opening the Backups screen to seeing
   the dashboard. Target under 2 minutes.

### D. Automatic backups and warnings (US3)
1. **Turn off**: turn automatic backups off. The dashboard shows "Automatic backups are off."
2. **Turn on**: turn them back on. The warning goes away.
3. **Once a day**: quit and reopen FloorPro. No second automatic backup is made the same day.

### E. Folder, copies and another computer (US4)
1. **Choose a folder**: press **Choose folder…** and pick a USB drive or a cloud-synced
   folder. Press **Back up now**, and the file appears in that folder.
2. **Folder missing**: remove the USB drive and press **Back up now**. A plain-English error
   appears, and no partial file is left. Reopen FloorPro the next day (or set
   `last_auto_date` back a day in `backup-settings.json`). The automatic backup lands on
   this computer, and the dashboard warns that the folder couldn't be reached.
3. **Save a copy to…**: on any backup, use **Save a copy to…** and choose the Desktop. The
   copy is identical in size.
4. **Another computer**: on a second install (or a second empty `FLOORPRO_DATA_DIR`), set a
   *different* password, then use **Restore from a file…** on the copy from step 3. FloorPro
   asks for the backup's password.
   - **Wrong password**: "That password doesn't open this backup."
   - **Right password**: everything is restored.
5. **Mac ↔ Windows**: if a Windows PC or VM is available, repeat step 4 there with a backup
   made on the Mac (SC-006). CI covers this with the committed fixture.

### F. Change password (US5-4)
1. **Change it**: **Change password**, entering the current password, then a new one twice.
   The notice explains that old backups keep their old password.
2. **Old backup**: restore a backup made before the change. FloorPro asks for the old
   password.

### G. Damaged and unsuitable files (edge cases)
1. **Not a backup**: rename any PDF to `test.fpbackup`, then use **Restore from a file…** →
   "This file isn't a FloorPro backup, or it's damaged." Nothing changes.
2. **Damaged**: copy a backup, change a few bytes near the end with a hex editor, and restore
   it. FloorPro says the backup is damaged, and current data is unchanged.

### H. Startup recovery (FR-025)
1. **Damage the database**: quit FloorPro. In `dev-data`, overwrite the start of
   `floorpro.db` (for example `printf 'garbage' | dd of=dev-data/floorpro.db bs=1 seek=0
   conv=notrunc`).
2. **Recovery screen**: start FloorPro. The recovery screen appears instead of a crash.
3. **Restore**: choose **Restore this backup**. The dashboard opens with the data restored,
   and the damaged file is in `dev-data/damaged/`.

## Performance spot-checks

With 10,000 customers (the slow tests seed them):
- **Back up now**: under 10 s (SC-001).
- **Restore**: under 30 s (SC-002).
- **First-time restore by a user**, Backups screen to dashboard: under 2 minutes (SC-005).
- **Opening FloorPro** with an automatic backup due: no more than 1 s slower (SC-007).
