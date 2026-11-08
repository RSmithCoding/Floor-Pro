# UI Route Contract: Backups and Recovery

**Feature**: 002-backup-restore

The response conventions are the same as feature 001
([../../001-settings-customer-records/contracts/routes.md](../../001-settings-customer-records/contracts/routes.md)):

- **Pages and partials**: full page, or the partial for an HTMX request.
- **Validation errors**: `422` with errors inline.
- **Success**: HTMX success uses `HX-Push-Url` + an out-of-band toast. A plain request gets a
  `303` + flash cookie.
- **Dialogs**: dialogs open into `#modal`, and errors are sent back with `HX-Retarget: #modal`.

**Identifying a backup**: `{loc}` is `local` or `folder`, and `{name}` is the file name. Both
are checked against the patterns in [data-model §1](../data-model.md#1-backup-a-file). An
unknown or invalid value returns `404`.

**Desktop vs browser**: when `app.state.dialogs` is set (the desktop window), the controls
marked 🖥 use native dialogs. Otherwise (`--browser`, tests without a fake) the controls marked
🌐 are shown instead.

## Navigation and dashboard

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| GET | `/` | Dashboard (existing), plus a **Backups** card from `backup_status` ([data-model §4](../data-model.md#4-dashboard-backup-status-derived-not-stored)) linking to `/backups`. Opening it also triggers the daily automatic-backup check (research §9) | Full page |
| — | nav | A **Backups** item is added to the main navigation (FR-001) | |

## Backups screen

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/backups` | Backups screen | none | **No password set** → the "Set a backup password" form only (`backups/_set_password.html`). **Otherwise**: **Back up now**, location panel (folder or "This computer"), automatic on/off, **Restore from a file…**, **Change password**, and the list (`backups/_list.html`): newest first, with date/time (local), type badge, size, customers, location, and actions **Restore**, **Save a copy to…**, **Delete** (Delete hidden for the most recent successful) |
| POST | `/backups/password` | Set the first password | `password`, `password_confirm` | **Invalid** → `422` form (research §15 messages). **Already set** → `409`. **OK** → derive and store key, convert legacy pre-upgrade copies, show `/backups` + toast "Backup password set". Then the first automatic backup runs if automatic backups are on |
| GET | `/backups/password/change` | Change-password dialog | none | `<dialog>` with `current_password`, `password`, `password_confirm` and the notice "Backups you've already made still need the password they were made with." |
| POST | `/backups/password/change` | Change it | as above | **Invalid / wrong current** → `422` back into `#modal`. **OK** → `/backups` + toast "Backup password changed" |
| POST | `/backups` | **Back up now** | none | **OK** → `/backups` with the new backup at the top + toast "Backup made · 1,234 customers". **Folder unreachable / disk full / no password / busy** → `200` `/backups` with an error toast in plain English (US1-3), and no file left behind. The button has `hx-indicator` and shows "Backing up…" |
| POST | `/backups/automatic` | Turn automatic backups on/off | `auto_enabled` (`on` or absent) | `/backups` + toast "Automatic backups on" / "Automatic backups off" |
| POST | `/backups/folder/choose` 🖥 | Pick a folder with the native picker | none | **Cancelled** → `204`. **Not writable** → `/backups` with error toast. **OK** → save to preferences, `/backups` + toast "Backups will be saved to {folder}" |
| POST | `/backups/folder` 🌐 | Set the folder by path | `folder` | **Invalid** → `422` with "Choose a folder FloorPro can save to." **OK** → as above |
| POST | `/backups/folder/reset` | Go back to saving on this computer | none | `/backups` + toast "Backups will be saved on this computer". Existing files in the folder are left where they are |

## One backup

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/backups/{loc}/{name}/restore` | Restore confirmation dialog | none | `<dialog>`: date/time, type, customers, app version, the warning "Everything changed since then will be replaced. FloorPro will first save a Before restore backup of your current data." and the erased-customers note (research §17), a `confirm` field ("Type RESTORE"), and a `password` field only when `needs_password`. **Newer / damaged / unprotected legacy copy** → the dialog shows the refusal message (for a legacy copy: "This older copy isn't protected. It can only be restored from the recovery screen.") and no Restore button |
| POST | `/backups/{loc}/{name}/restore` | Restore it | `confirm`, `password` (if needed) | **Validation / wrong password** → `422` back into `#modal`, nothing changed. **Damaged / newer / Before restore backup failed** → `422` in `#modal` with the message, and current data unchanged (FR-011–FR-014). **OK** → `HX-Redirect: /` (full reload, so every screen shows restored data) + flash "Restored the backup from 3 Nov 2026, 17:30" |
| POST | `/backups/{loc}/{name}/save-copy` 🖥 | **Save a copy to…** | none | Native Save dialog, suggesting the same file name. **Cancelled** → `204`. **OK** → toast "Saved a copy to {path}". **Error** → error toast |
| GET | `/backups/{loc}/{name}/download` 🌐 | **Save a copy to…** in a browser | none | `200` `application/octet-stream`, `Content-Disposition: attachment` |
| GET | `/backups/{loc}/{name}/delete` | Delete confirmation dialog | none | `<dialog>` "Delete the backup from {date}? This can't be undone." **Most recent successful** → `409` dialog explaining it can't be deleted |
| POST | `/backups/{loc}/{name}/delete` | Delete it | none | `/backups` + toast "Backup deleted". **Most recent successful** → `409` |

## Restore from a file

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| POST | `/backups/restore-file/choose` 🖥 | Pick a file with the native Open dialog | none | **Cancelled** → `204`. **Picked** → the same restore dialog as above, carrying a signed `source_token` instead of `{loc}/{name}` |
| POST | `/backups/restore-file/upload` 🌐 | Upload a file | multipart `file` | Saved to `<data dir>/tmp/`, then the same dialog with `source_token`. **Not a backup** → `422` message |
| POST | `/backups/restore-file/confirm` | Restore it | `source_token`, `confirm`, `password` | As `POST /backups/{loc}/{name}/restore`. **Token invalid or file gone** → `409` "That file is no longer available. Choose it again." |

## Recovery (only while in recovery mode)

While `app.state.recovery` is set, every request except `/static/*`, `/healthz` and
`/recovery*` gets a `303` to `/recovery` (or `HX-Redirect: /recovery` for HTMX). When the app
is not in recovery mode, `/recovery*` returns `404`.

| Method | Path | Purpose | Request | Response |
|--------|------|---------|---------|----------|
| GET | `/recovery` | Recovery screen (standalone layout: it doesn't need settings from the database) | none | The explanation, the most recent backup (if any) with **Restore this backup**, the list of other backups, **Restore from a file…**, and **Start with no data** |
| POST | `/recovery/restore` | Restore a listed backup | `loc`, `name`, `password` (if needed) | Moves the damaged files to `damaged/`, restores (no Before restore backup, research §13), rebuilds the engine, leaves recovery mode → `303 /` + flash "Restored the backup from …". **Errors** → `422` recovery screen with the message |
| POST | `/recovery/restore-file/choose` 🖥 · `/recovery/restore-file/upload` 🌐 · `/recovery/restore-file/confirm` | Restore from a file | as the Backups versions | as above |
| POST | `/recovery/start-fresh` | Start with no data | `confirm` (`START AGAIN`) | Moves the damaged files to `damaged/`, creates a new database, leaves recovery mode → `303 /` + flash "Started with no data. The damaged data was kept in {folder}." |

## Integration test coverage

Every row above has at least one test (Principle III). Desktop-only rows (🖥) use a fake
`app.state.dialogs`, and browser-only rows (🌐) use the default `None`.
