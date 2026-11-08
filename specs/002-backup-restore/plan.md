# Implementation Plan: Backup and Restore

**Branch**: `main` (no feature branch; Spec Kit labels it `002-backup-restore`) |
**Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-backup-restore/spec.md`

## Summary

Shop staff can back up all of FloorPro's data on demand or automatically each day, keep
backups in a folder they choose (USB or cloud-synced), save copies anywhere, and restore any
backup, including one from another Mac or Windows PC, without restarting. Every backup is
protected with the shop's backup password. If the database can't be opened at startup,
FloorPro shows a recovery screen instead of crashing.

**Technical approach** ([research.md](research.md)):

- **Making a backup**: a consistent snapshot of `floorpro.db` taken with SQLite's online
  backup API, compressed with zlib, encrypted with AES-256-GCM (key from scrypt) and written
  atomically as one `.fpbackup` file. A plaintext, authenticated header lets the screen list
  backups without the password.
- **Restoring**: the file is decrypted, checked and upgraded in a temporary copy first. Then a
  "Before restore" backup is made, and the backup API swaps the copy into the live database in
  a single transaction.
- **Stored outside the database**: preferences and the derived key are JSON files in the data
  folder, so a restore never rewinds them.
- **Schema**: no tables are added and no migration is needed.

## Technical Context

**Language/Version**: Python 3.13 (uv, `.python-version`)

**Primary Dependencies**: Existing stack (FastAPI, SQLAlchemy 2.x, Alembic, Jinja2, HTMX,
Tailwind, pywebview). **New**: `cryptography` (AES-256-GCM only; scrypt, HMAC and zlib come
from the standard library). Justified in research §3.

**Storage**: SQLite `floorpro.db` (unchanged schema). New files in the data folder:
`backup-key.json`, `backup-settings.json`, `backups/*.fpbackup`, `tmp/`, `damaged/`. Optional
chosen backup folder.

**Testing**: pytest + `TestClient`. Unit tests are written first for the file format, crypto,
retention, status and password rules. Integration tests cover every route, with a fake
native-dialogs object. A committed cross-platform fixture backup, plus fault-injection and
slow performance tests.

**Target Platform**: macOS (dev: macOS 12 Intel) and Windows 10/11. CI matrix on both.

**Project Type**: Desktop app (local FastAPI server in a pywebview window), single package.

**Performance Goals**: Back up 10,000 customers in under 10 s (SC-001). Restore, including
the safety backup, in under 30 s (SC-002). Startup delayed by no more than 1 s (SC-007). Pages
under 300 ms.

**Constraints**: Fully offline, with no network or cloud APIs. Restore is all-or-nothing.
Byte-identical file format across OSes. The password is never stored. Must work frozen by
PyInstaller.

**Scale/Scope**: One shop per install. Databases from a few MB up to a few hundred MB. Dozens
of backups. About 8 new screens or dialogs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle / rule | How this plan complies | Pre-design | Post-design |
|---|------------------|------------------------|:---------:|:-----------:|
| I | Local-first, offline | Backups are local files. A chosen folder may be cloud-synced by the shop's own client; FloorPro never uploads | ✅ | ✅ |
| I | Backup & restore mechanism (release blocker) | Delivered by this feature: manual, automatic, restore, off-computer copies | ✅ | ✅ |
| I | Auto backup before migrations | Kept. Protected once a password is set (research §11) | ✅ | ✅ |
| I | Schema changes via Alembic | No schema change. Restored older backups are upgraded with Alembic on a staged copy (research §8) | ✅ | ✅ |
| I | Confirm destructive actions | Restore needs `RESTORE` typed. Delete has a confirm dialog. Start with no data needs `START AGAIN`. Damaged data is moved aside, never deleted | ✅ | ✅ |
| I | Personal data protection | Backups are always encrypted (SC-008). Erasure caveat shown on restore (research §17) | ✅ | ✅ |
| II | Money/measurement accuracy | Not touched. Backups copy the database bit for bit, so stored minor units are preserved exactly | ✅ | ✅ |
| III | Test-first for rules | Format, crypto, retention, status and password rules: unit tests first | ✅ | ✅ |
| III | Integration test per route | Every row of [contracts/routes.md](contracts/routes.md) | ✅ | ✅ |
| III | Migration tests | Restore of an older-revision backup is upgraded (research §16) | ✅ | ✅ |
| IV | Python only, server-rendered, minimal JS | Jinja + HTMX. Progress via `hx-indicator`. **No new JavaScript** (dialogs reuse `app.js`) | ✅ | ✅ |
| IV | Assets bundled | No new front-end assets | ✅ | ✅ |
| V | Shared components, feedback, plain errors, 300 ms, WCAG AA | Reuses card/button/field/modal/table/badge/toast. Every failure has a plain-English message. Dashboard card reads one small JSON file | ✅ | ✅ |
| V | Dashboard shows vital info | Backup warning card (FR-020) | ✅ | ✅ |
| VI | Layering | Routes → `backup_service`/`recovery_service` → `backup_file` (format) + `domain/backups.py` (pure rules) | ✅ | ✅ |
| VI | Single process; no background workers without justification | One short-lived thread per automatic backup. **Justified in Complexity Tracking** | ⚠️ | ✅ |
| VI | Justified, PyInstaller-compatible dependencies | `cryptography`: unavoidable for encryption (no AES in stdlib), wheels for macOS/Windows, PyInstaller hook built in | ✅ | ✅ |
| Platform | `pathlib`, data dir, platform code isolated | Data and FloorPro's own backups stay in the app-data directory; the chosen folder and saved copies are permitted by constitution v1.1.1 and are always encrypted. Native dialogs stay in `desktop.py`. File format is OS-independent. Atomic writes via `os.replace` (works on both OSes) | ✅ | ✅ |
| Platform | Logging without unnecessary customer data | Logs record file names, sizes and errors. Never passwords, keys or record contents | ✅ | ✅ |
| Workflow | CI on macOS + Windows | Unchanged workflow. The new fixture test runs on both | ✅ | ✅ |

**Gate result**: PASS. The one item flagged before design (background thread) is justified
below.

## Project Structure

### Documentation (this feature)

```text
specs/002-backup-restore/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── routes.md            # UI/HTTP route contract
│   └── backup-file.md       # .fpbackup format (long-lived)
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
pyproject.toml                    # + cryptography
scripts/
└── make_backup_fixture.py        # NEW: builds tests/fixtures/backup-v1.fpbackup (run once)

src/floorpro/
├── __init__.py                   # + __version__ (package metadata, with a fallback)
├── paths.py                      # + tmp_dir(), damaged_dir(), backup_key_path(), backup_prefs_path()
├── migrate.py                    # backup_if_needed(): protected .fpbackup once a key exists;
│                                 #   upgrade_to_head(path, backup=True) flag for staged restores
├── backup_file.py                # NEW: .fpbackup read/write, header, scrypt key + key id,
│                                 #   AES-GCM, atomic write (no DB/web imports)
├── domain/
│   └── backups.py                # NEW (pure): BackupKind, filename_for(), parse names,
│                                 #   select_for_pruning(), most_recent(), backup_status(),
│                                 #   validate_new_password()
├── services/
│   ├── backup_service.py         # NEW: key + prefs files, list, make_backup, restore,
│                                 #   delete, save_copy, retention, maybe_run_daily, lock
│   └── recovery_service.py       # NEW: startup check, move aside, start fresh
├── schemas/
│   └── backup_forms.py           # NEW: password / restore confirm form parsing → field errors
├── routes/
│   ├── backups.py                # NEW: /backups*
│   ├── recovery.py               # NEW: /recovery*
│   └── dashboard.py              # + backup card, daily check
├── app.py                        # lifespan: recovery detection, daily check, app.state.dialogs,
│                                 #   app.state.run_in_background, recovery middleware, routers
├── desktop.py                    # Dialogs class: save_path(), choose_folder(), open_file();
│                                 #   customer export switched to save_path()
└── templates/
    ├── base.html                 # + Backups nav item
    ├── dashboard.html            # + backup card
    ├── backups/                  # index.html, _set_password.html, _panel.html, _list.html,
    │                             #   _confirm_restore.html, _confirm_delete.html, _change_password.html
    └── recovery/                 # index.html (standalone layout), _restore_form.html

tests/
├── fixtures/backup-v1.fpbackup   # NEW: committed cross-platform fixture
├── unit/
│   ├── test_backup_file.py       # round trip, tamper, truncation, wrong password vs damaged, NFC
│   ├── test_backups_domain.py    # names, retention, most recent, status, password rules
├── integration/
│   ├── test_backups_password.py
│   ├── test_backups_make.py      # incl. concurrent writes, unwritable folder, privacy (SC-008)
│   ├── test_backups_restore.py   # exactness, fault injection, newer/older, wrong password
│   ├── test_backups_files.py     # folder choose/reset, save copy, download, restore from file
│   ├── test_backups_auto.py      # daily, retention, fallback, dashboard card
│   ├── test_recovery.py
│   ├── test_backups_perf.py      # @slow: 10,000 customers
│   └── test_accessibility.py     # + backups pages and dialogs
└── migrations/test_migrations.py # + restore of an older-revision backup is upgraded
```

**Structure Decision**: The single package from feature 001 is kept. The file format sits in
its own module (`backup_file.py`) because it's a long-lived contract with no database or web
dependencies. Rules that can be pure (`domain/backups.py`) are tested first. Orchestration
lives in services, in line with Principle VI.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|------|------------|--------------------------------------|
| One background thread for the automatic backup | SC-007: startup must not wait for a backup, and US3-1 says "in the background without slowing the user down" | Running it in the startup path would delay opening FloorPro by the backup time. A scheduler, queue or separate process is far more machinery for one daily job. The thread is short-lived, guarded by the backup lock, and replaced by a synchronous runner in tests |
| New dependency `cryptography` | FR-026 requires encrypted backups. The stdlib has no AES | A pure-Python AES is slow and unaudited. SQLCipher and keyring add native builds or OS prompts. `cryptography` is the de facto standard, with PyInstaller support |

## Post-design Constitution re-check

Re-evaluated after writing [data-model.md](data-model.md), [contracts/](contracts/) and
[quickstart.md](quickstart.md):

- **No schema change.** The new state is in files, by design, so restores can't rewind it.
- **No new JavaScript.**
- **Layering holds.** Routes only parse forms, call services and render.
- **Destructive actions** all have confirmations.
- **Background thread**: the only flagged item, justified above.

**Result: PASS.**
