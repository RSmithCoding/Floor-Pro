---

description: "Task list for 002-backup-restore"
---

# Tasks: Backup and Restore

**Input**: Design documents from `/specs/002-backup-restore/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/routes.md,
contracts/backup-file.md, quickstart.md

**Tests**: Included. The constitution (Principle III) makes them mandatory:
- test-first for the file format, encryption, retention, status and password rules
- an integration test for every route in contracts/routes.md
- a migration test for restoring older backups

Write each test task before its implementation task, and confirm it **fails** first.

**Organization**: Tasks are grouped by user story. **US5 (password) comes first**, because no
backup can be made until a password is set (FR-027). After that come US1 (back up now) and US2
(restore, with startup recovery), which together with US5 form the MVP. Then US3 (automatic)
and US4 (folder, copies, restore from a file).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: User story the task belongs to (US1–US5)

## Path Conventions

Single package, src layout: `src/floorpro/…`, `tests/…`, `scripts/…` at the repository root
(see plan.md → Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependency, paths and test scaffolding

- [X] T001 Add the `cryptography` runtime dependency with `uv add cryptography`. Pick a release at least 2 weeks old with wheels for macOS x86_64/arm64 and Windows x64 on Python 3.13. Confirm `uv.lock` is updated and `uv sync --locked` succeeds. Record the reason (AES-256-GCM only; research §3) in a comment beside the dependency in `pyproject.toml`
- [X] T002 [P] Extend `src/floorpro/paths.py`. Each new helper creates its folder if needed, and every new path comes from these helpers:
  - `tmp_dir()` → `data_dir()/"tmp"`
  - `damaged_dir()` → `data_dir()/"damaged"`
  - `backup_key_path()` → `data_dir()/"backup-key.json"`
  - `backup_prefs_path()` → `data_dir()/"backup-settings.json"`
  - Also add `__version__` to `src/floorpro/__init__.py`: it reads `importlib.metadata.version("floorpro")` and falls back to `"0.0.0+unknown"` when the metadata is missing (as can happen in a frozen build)
- [X] T003 [P] Create `tests/fixtures/` (with a `README.md` saying the files there are long-lived contract fixtures that must not be regenerated in a way that changes the format). Add these fixtures to `tests/conftest.py`:
  - `fast_kdf`: autouse; monkeypatches `floorpro.backup_file.DEFAULT_KDF` to `n=2**10, r=8, p=1`
  - `fake_dialogs`: an object with `save_path(filename)`, `choose_folder()` and `open_file()` returning paths the test sets, or `None`
  - `sync_background`: sets `app.state.run_in_background = lambda fn: fn()`
  - `backup_password`: sets the password `"correct horse battery"` through the service
  - `db_dump(path)`: helper returning `"\n".join(sqlite3.connect(path).iterdump())` for exactness checks

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The file format, the pure rules, the key and preference stores, listing, and
the native-dialogs hook that every story uses

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests first (must fail before implementation)

- [X] T004 [P] Write `tests/unit/test_backup_file.py` for the format in contracts/backup-file.md:
  - **Round trip**: `write_backup(path, db_bytes, header_fields, key, kdf)` then `read_header(path)` and `decrypt(path, key)` return identical bytes
  - **Layout**: the file starts with the 16-byte magic `b"FLOORPRO-BACKUP\x00"`, then a 4-byte big-endian header length, then a UTF-8 JSON header containing every key in the contract table (`format_version`, `kind`, `created_at`, `app_version`, `schema_revision`, `contents`, `cipher`, `compression`, `kdf`, `key_id`, `nonce`)
  - **Tampering and damage**: changing one header byte → `BackupDamaged`. Flipping one payload byte → `BackupDamaged`. Truncating the file → `BackupDamaged`. A random file or a PDF header → `NotABackup`
  - **Newer files**: `format_version: 2` → `BackupTooNew`
  - **Wrong password**: `derive_key("wrong…", kdf)` (where `kdf: KdfParams` carries the salt) gives a key id that doesn't match → `WrongPassword`, distinct from `BackupDamaged`
  - **Key id**: equals `HMAC-SHA256(key, b"floorpro-backup-key-id")[:16]`
  - **NFC**: `derive_key("café…" NFD, kdf)` == `derive_key("café…" NFC, kdf)`
  - **Nonces**: are unique across two writes
  - **Header validation**: a header over 65,536 bytes is rejected
  - **Defaults**: `DEFAULT_KDF` is `n=131072, r=8, p=1` when not monkeypatched (a test that undoes `fast_kdf`)
- [X] T005 [P] Write `tests/unit/test_backups_domain.py` for `floorpro.domain.backups`:
  - **`BackupKind`**: values `manual`, `automatic`, `before_restore`, `before_upgrade`, with labels "Manual", "Automatic", "Before restore", "Before upgrade"
  - **`filename_for(kind, local_dt, existing_names)`**: returns `FloorPro-backup-2026-11-08-173012-manual.fpbackup`, appends `-2`, `-3`… on collision, and uses `before-restore`/`before-upgrade` with hyphens
  - **`parse_filename`**: accepts names matching `^FloorPro-backup-\d{4}-\d{2}-\d{2}-\d{6}-(manual|automatic|before-restore|before-upgrade)(-\d+)?\.fpbackup$` and legacy `^floorpro-\d{8}T\d{12}Z-pre-[0-9a-z_]+\.db$`. It rejects `../x.fpbackup`, absolute paths and other names
  - **`select_for_pruning(backups)`**: returns automatic backups beyond the newest 14 and before-upgrade beyond the newest 10. It never returns manual or before-restore backups
  - **`most_recent(backups)`**: the newest `created_at`, ignoring damaged entries
  - **`backup_status(prefs, key_set, now)`**: messages and order exactly as in the data-model §4 table, including "No backups yet." vs "No backup in the last 7 days." at exactly 7 days and 7 days + 1 second
  - **`validate_new_password(password, confirm)`**: returns `{"password": "Use at least 10 characters."}` for 9 characters, for only spaces, and for over 1,024 characters (message "Use at most 1,024 characters."). Returns `{"password_confirm": "The two passwords don't match."}` on mismatch. Returns `{}` for a valid pair. Length is counted after NFC

### Implementation

- [X] T006 Implement `src/floorpro/backup_file.py`, importing only the stdlib and `cryptography` (no database or web imports), to make T004 pass:
  - **Constants**: `MAGIC`, `FORMAT_VERSION = 1`, `MAX_HEADER = 65536`, `KdfParams(n, r, p, salt)` (frozen dataclass; the salt lives inside it), `DEFAULT_KDF = KdfParams(n=131072, r=8, p=1, salt=b"")`, `EXTENSION = ".fpbackup"`
  - **Exceptions**: `NotABackup`, `BackupDamaged`, `BackupTooNew`, `WrongPassword`, each carrying the user message from contracts/backup-file.md
  - **Key handling**: `new_kdf() -> KdfParams` (`DEFAULT_KDF` with a fresh 16-byte salt) and `derive_key(password, kdf: KdfParams)` (NFC + UTF-8 + `hashlib.scrypt(..., maxmem=256 * 1024 * 1024)`), plus `key_id(key)`
  - **Reading**: `read_header(path) -> dict`, which reads only the prefix, validates required keys, and checks `format_version` and `cipher`/`compression`
  - **Writing**: `write_backup(target_dir, filename, db_bytes, fields, key, kdf) -> Path`. It zlib level 6 compresses, encrypts with AES-GCM using the magic + length + header bytes as associated data, and writes atomically via `.FloorPro-<random>.partial` + flush + `os.fsync` + `os.replace`, removing the partial file on any exception
  - **Decrypting**: `decrypt(path, key) -> bytes`
  - **Helper**: `atomic_copy(src, dest)` for save-a-copy
- [X] T007 [P] Implement `src/floorpro/domain/backups.py` (pure, no I/O) to make T005 pass:
  - **Types**: `BackupKind`, and a `BackupInfo` dataclass (fields per data-model §1: `location`, `filename`, `kind`, `created_at`, `app_version`, `schema_revision`, `contents`, `size_bytes`, `protected`, `key_id`, `damaged`, plus `needs_password(current_key_id)`)
  - **Constants**: `KEEP_AUTOMATIC = 14`, `KEEP_BEFORE_UPGRADE = 10`, `STALE_AFTER = timedelta(days=7)`
  - **Functions**: `filename_for`, `parse_filename`, `select_for_pruning`, `most_recent`, `BackupWarning`, `backup_status` and `validate_new_password`, with the exact messages from data-model §4 and §6
- [X] T008 Create `src/floorpro/services/backup_service.py`, part 1: stores, listing and lock (depends on T006, T007):
  - **`BackupPrefs`** dataclass with the defaults from data-model §3. `load_prefs()` treats a missing or invalid file as defaults and ignores unknown fields. `save_prefs(prefs)` writes atomically
  - **`load_key() -> StoredKey | None`**: missing or invalid file → `None`, with a logged warning when invalid. `key_is_set()`
  - **`LOCK = threading.Lock()`** and an `acquire(timeout=60)` context manager that raises `BackupBusy("A backup is already in progress. Try again in a moment.")`
  - **`locations() -> dict[str, Path]`**: `local` = `paths.backups_dir()`, plus `folder` if prefs has one. It's always listed even when unreachable, flagged `reachable=False`
  - **`resolve(loc, name) -> Path`**: checks `parse_filename`, and that the resolved path is inside the location folder (else `LookupError` → 404)
  - **`list_backups() -> list[BackupInfo]`**: newest first, across both locations. It reads headers only, turns legacy `.db` files into `before_upgrade` with `protected=False` (time from the name stamp), and marks unreadable files `damaged=True`
  - **`cleanup_partials()`**: removes `.FloorPro-*.partial` files older than one day from both locations, and empties `tmp_dir()`
- [X] T009 [P] Refactor the native-dialogs hook. Export behaviour is unchanged; `test_customers_export.py` switches from `save_file` to `fake_dialogs`:
  - **`src/floorpro/desktop.py`**: replace `_native_saver` with a `NativeDialogs` class providing `save_path(filename) -> Path | None` (Documents folder default), `choose_folder() -> Path | None` (`webview.FileDialog.FOLDER`) and `open_file() -> Path | None` (`webview.FileDialog.OPEN`, `file_types=("FloorPro backups (*.fpbackup)", "All files (*.*)")`). Set `app.state.dialogs = NativeDialogs(webview, window)`
  - **`src/floorpro/app.py`**: replace `app.state.save_file = None` with `app.state.dialogs = None`, and add `app.state.run_in_background` defaulting to starting a daemon `threading.Thread`
  - **`src/floorpro/routes/customers.py`**: the customer export save route now calls `dialogs.save_path(filename)` and writes the bytes itself
  - **Tests**: update `tests/integration/test_customers_export.py` to use `fake_dialogs`
  - **Dialog unit test**: write `tests/unit/test_desktop_dialogs.py`. It drives `NativeDialogs` with a stub `webview` module (with `FileDialog.SAVE/FOLDER/OPEN`) and a stub window whose `create_file_dialog` records its arguments and returns a str, a tuple or `None`. Assert the dialog type, `file_types`, the default directory and the returned `Path`/`None`. It runs on macOS and Windows CI
- [X] T010 [P] Add a **Backups** item to the main navigation in `src/floorpro/templates/base.html`, after Customers and before Settings, with `nav = "backups"`, linking to `/backups`, using an outline "archive box" icon like the other items (FR-001)
- [X] T011 Create `src/floorpro/routes/backups.py` with an `APIRouter`, and register it in `src/floorpro/app.py`. Then create `src/floorpro/templates/backups/index.html` (extends `base.html`, title "Backups · FloorPro", `nav = "backups"`). It renders the `_set_password.html` partial when `key_is_set()` is false, and otherwise `_panel.html` + `_list.html`. Start with placeholder partials that later stories fill in. Add `GET /backups` and one integration test in `tests/integration/test_backups_password.py` checking that the page renders with the nav item marked `aria-current="page"`

**Checkpoint**: The format and rules are tested, the stores and listing work, and the Backups
screen exists.

---

## Phase 3: User Story 5 - Password-protected backups (Priority: P1) 🎯 MVP prerequisite

**Goal**: A backup password is set before anything else, remembered on this computer as a
derived key (never the password itself), and can be changed. "Before upgrade" copies become
protected.

**Independent Test**: Open Backups, see only the set-password form, fail the length and match
rules, set a valid password, and confirm `backup-key.json` holds a key and key id but no
password text. Change the password with the current one, and confirm the key id changes.

### Tests for User Story 5

- [X] T012 [P] [US5] Extend `tests/integration/test_backups_password.py` (created in T011). Flash and toast text is exact:
  - **No password yet**: `GET /backups` shows only the set-password form, with `type="password"`, `autocomplete="new-password"`, and the warning text from research §15
  - **Invalid entries**: `POST /backups/password` with 9 characters → `422` "Use at least 10 characters." Mismatch → `422` "The two passwords don't match." The entered passwords are never echoed back in the response HTML
  - **Valid entry**: → toast "Backup password set". `backup-key.json` exists, its `key_id` equals `key_id(base64-decoded key)`, and the file doesn't contain the password string
  - **Already set**: a second `POST /backups/password` → `409`
  - **Change dialog**: `GET /backups/password/change` dialog contains "Backups you've already made still need the password they were made with."
  - **Change, invalid**: `POST /backups/password/change` with an empty current password → `422` "Enter your current backup password.", returned into `#modal` (`HX-Retarget: #modal`). Wrong current → `422` "That isn't the current backup password."
  - **Change, valid**: → toast "Backup password changed", and `key_id` and salt both differ from before
- [X] T013 [P] [US5] Add to `tests/migrations/test_migrations.py`:
  - **No password**: `backup_if_needed` still writes a plain `floorpro-*-pre-*.db`
  - **Password set**: it writes a protected `FloorPro-backup-*-before-upgrade.fpbackup` into `backups/` only, with header `kind == "before_upgrade"`, and keeps at most 10
  - **Setting the password**: converts existing legacy `.db` pre-upgrade copies to `.fpbackup` (with `created_at` from the name stamp) and deletes the plain files

### Implementation for User Story 5

- [X] T014 [P] [US5] Create `src/floorpro/schemas/backup_forms.py` with `parse_new_password(form) -> (values, errors)` using `domain.backups.validate_new_password`, `parse_change_password(form, check_current)` returning the errors from data-model §6, and `parse_restore_confirm(form, needs_password)`. The confirm must be `RESTORE` with surrounding spaces trimmed, in any case ("Type RESTORE to confirm."). The password is required when `needs_password` ("Enter the password this backup was made with.")
- [X] T015 [US5] Add to `src/floorpro/services/backup_service.py`:
  - **`set_password(password)`**: raises `PasswordAlreadySet` if a key exists. Otherwise it calls `new_kdf()`, derives the key with `derive_key(password, kdf)`, and writes `backup-key.json` atomically with the fields in data-model §2 (`version`, `kdf`, `key`, `key_id`, `set_at`). It then calls `protect_legacy_upgrade_copies()`
  - **`check_current_password(password) -> bool`**: derives the key with the stored `KdfParams` (including its salt) and compares key ids with `hmac.compare_digest`
  - **`change_password(current, new)`**: makes a fresh salt and key, and replaces the file atomically
  - **`protect_legacy_upgrade_copies()`**: converts every legacy `.db` in `backups/` (customer count via `SELECT COUNT(*) FROM customer` when the table exists, `schema_revision` from `alembic_version`), then unlinks the plain file only after the protected file is written
  - **Logging**: never log passwords or keys
- [X] T016 [US5] Update `src/floorpro/migrate.py` (makes T013 pass):
  - **`backup_if_needed(db_path)`**: when `backup_service.load_key()` returns a key, snapshot with the backup API into `paths.tmp_dir()` and write a protected `before_upgrade` backup to `paths.backups_dir()` via `backup_file.write_backup`. Then prune `before_upgrade` backups to `KEEP_BEFORE_UPGRADE` (10). Without a key, keep the existing plain `.db` behaviour
  - **`upgrade_to_head(db_path, backup=True)`**: add a keyword flag so staged restores can skip the pre-upgrade copy
  - **Imports**: avoid a circular import by importing `backup_service` inside the function
- [X] T017 [US5] Add the routes to `src/floorpro/routes/backups.py`: `POST /backups/password`, `GET /backups/password/change` and `POST /backups/password/change`, following contracts/routes.md. Errors in the dialog use `HX-Retarget: #modal` + `HX-Reswap: innerHTML`, and the set form uses `HX-Retarget: #backup-password-form`. (The first automatic backup after setting the password is wired up in T039, once US3 exists)
- [X] T018 [P] [US5] Create the templates `src/floorpro/templates/backups/_set_password.html` and `src/floorpro/templates/backups/_change_password.html`, built only from the shared `field`, `button`, `card` and `modal` components:
  - **Set password**: card form `id="backup-password-form"` with the research §15 warning in a callout, and fields `password`/`password_confirm`
  - **Change password**: `<dialog>` with `aria-labelledby` pointing at its title, `current_password` (`autocomplete="current-password"`), `password` and `password_confirm`

**Checkpoint**: A password can be set and changed. Pre-upgrade copies are protected.

---

## Phase 4: User Story 1 - Back up now (Priority: P1) 🎯 MVP

**Goal**: **Back up now** writes a complete, consistent, protected backup, and the list shows
every backup.

**Independent Test**: Set a password, add customers, press **Back up now**, and see a Manual
entry at the top with date, size and customer count. The file contains no customer details,
and decrypting it gives a database with every customer.

### Tests for User Story 1

- [X] T019 [P] [US1] Write `tests/integration/test_backups_make.py`:
  - **Back up now**: `POST /backups` with a password set → toast "Backup made · 2 customers". The list's first row shows "Manual", the local date/time, a size like "12 KB", "2" customers and "This computer". The file in `backups/` matches the filename pattern, and its header has `kind == "manual"`, `contents.customers == 2` and `schema_revision == head_revision()`
  - **Exact contents**: decrypting with the stored key gives a database whose `db_dump` equals the live one
  - **No password**: → error toast, and no file
  - **Destination unwritable** (monkeypatch `backup_file.write_backup` to raise `OSError(ENOSPC)`): → plain-English error toast "There isn't enough space to save the backup.", no `.partial` or `.fpbackup` left, and `last_success_at` unchanged
  - **Consistent snapshot**: a second session holding an open write transaction on another thread while the backup runs; the backup completes, and the snapshot doesn't include the uncommitted row
  - **Privacy (SC-008)**: customers with distinctive name, phone, email and address strings; none appear in the file bytes in UTF-8 or UTF-16-LE
  - **Busy**: while `LOCK` is held → "A backup is already in progress. Try again in a moment." (with the timeout monkeypatched to 0.1 s)
- [X] T020 [P] [US1] Write `tests/integration/test_backups_list.py`. The list shows backups from both locations newest first, and labels:
  - legacy `.db` as "Before upgrade" + "Not protected"
  - damaged files as "Damaged or not a FloorPro backup"
  - before-upgrade `.fpbackup` as "Before upgrade" (FR-007, FR-008)
  - a file named `../evil.fpbackup` is never listed or resolvable (`GET /backups/local/..%2Fevil.fpbackup/restore` → 404)

### Implementation for User Story 1

- [X] T021 [US1] Add `make_backup(kind, destination=None) -> BackupInfo` to `src/floorpro/services/backup_service.py`, following research §7:
  - **Locking and key**: acquire `LOCK`, and require a key (else `NoPassword("Set a backup password first.")`)
  - **Snapshot**: take it with `sqlite3.connect(paths.db_path()).backup(dest)` into `tmp_dir()`
  - **Header fields**: `contents = {"customers": COUNT(*) FROM customer}`, `schema_revision` from `alembic_version`, `app_version` from `floorpro.__version__`, `created_at` = UTC now
  - **Writing**: name the file with `filename_for(kind, local now, existing names)` and write it with `write_backup` to `destination or (backups_dir() if kind in {BEFORE_RESTORE, BEFORE_UPGRADE} else current_destination())` (`current_destination()` = chosen folder if set, else `backups_dir()`). Before restore and Before upgrade backups are always local
  - **Clean-up and prefs**: delete the snapshot in `finally`, and update `last_success_at` (except for `before_upgrade`)
  - **Errors**: map `OSError` to `BackupFailed` with a plain-English message: `ENOSPC` → "There isn't enough space to save the backup."; `EACCES`/`EPERM`/`EROFS` → "FloorPro isn't allowed to save in {folder}."; missing folder → "The backup folder {folder} can't be reached. Is the drive plugged in?"; anything else → "The backup couldn't be saved." Log the technical detail
- [X] T022 [US1] Add `POST /backups` to `src/floorpro/routes/backups.py`. On success, render `/backups` with `HX-Push-Url: /backups` and the toast "Backup made · {n} customers" (n formatted with a thousands separator). On `BackupFailed`, `NoPassword` or `BackupBusy`, render `/backups` with an error toast. Never return a raw error
- [X] T023 [P] [US1] Fill in `src/floorpro/templates/backups/_panel.html` and `src/floorpro/templates/backups/_list.html` using the shared `card`, `button`, `table`, `badge` and `empty_state` components:
  - **Panel**: the **Back up now** button posts to `/backups` with `hx-indicator` and a hidden-until-requesting "Backing up…" spinner (CSS `.htmx-request` only, no new JS). The panel also shows "Saving to: This computer" (the folder controls come in US4)
  - **List table columns**: Date (`local_datetime`), Type badge, Size (human-readable), Customers, Location ("This computer" / folder name), Actions (placeholders for Restore, Save a copy, Delete, added in later stories)
  - **Empty state**: "No backups yet" with **Back up now**
  - **Damaged and not-protected rows**: shown with a neutral or warning badge
- [X] T024 [P] [US1] Add a `filesize` filter to `src/floorpro/templating.py` (bytes → "980 bytes", "12 KB", "2.4 MB", "1.1 GB", using 1,024 steps and one decimal above KB), with unit tests in `tests/unit/test_filesize_filter.py`

**Checkpoint**: Backups can be made and listed. **With US5, this delivers protection
without restore yet. Don't ship before US2.**

---

## Phase 5: User Story 2 - Restore from a backup (Priority: P1) 🎯 MVP

**Goal**: Restore any listed backup safely: confirmed by typing `RESTORE`, preceded by a
Before restore backup, all-or-nothing, no restart, and newer or damaged backups refused. It
also covers startup recovery when the database can't be opened (FR-025).

**Independent Test**: Back up, change and delete customers, restore, and confirm `db_dump` is
identical to the backed-up state and a Before restore backup exists. Then corrupt
`floorpro.db`, start the app, and restore from the recovery screen.

### Tests for User Story 2

- [X] T025 [P] [US2] Write `tests/integration/test_backups_restore.py`:
  - **Confirm dialog**: `GET /backups/local/{name}/restore` shows the date, "Manual", the customer count, the replacement warning and the erased-customers note from research §17, with a `confirm` field and **no** password field for this computer's backup
  - **Wrong confirmation**: `POST` with `confirm=restor` → `422` "Type RESTORE to confirm.", and data unchanged
  - **Success**: `confirm=restore` (any case) → `HX-Redirect: /` and the flash "Restored the backup from {local date, time}". `db_dump` equals the backed-up state (SC-003). The list now has a "Before restore" backup whose contents equal the pre-restore state (US2-4)
  - **No restart**: after restore, `GET /customers` shows the restored customers through the existing engine
  - **No self-lock**: a restore immediately after `GET /customers` and `GET /settings` in the same client succeeds within 2 s (no lock wait)
  - **Newer version**: a backup whose header has an unknown `schema_revision` → the dialog shows "This backup was made by a newer version of FloorPro. Update FloorPro first.", with no Restore button, and a `POST` → `422` with data unchanged
- [X] T026 [P] [US2] Write `tests/integration/test_backups_restore_faults.py` (SC-004). In each case the live `db_dump` is unchanged and `tmp/` is empty (no `restore-*.db`, `-wal` or `-shm` files):
  - a flipped payload byte → `422` "This backup is damaged and can't be used. Your current data hasn't been changed."
  - a truncated file → the same message
  - the Before restore backup failing (monkeypatch `make_backup` to raise `BackupFailed`) → `422` naming that failure, and no swap attempted
  - an exception raised inside the swap step (monkeypatch the swap's `backup` call to raise `sqlite3.OperationalError`) → `422`
  - a decrypted database failing `integrity_check` → the damaged message
  - a database missing `business_settings` → the damaged message
  - **Folder unreachable** (not a failure case): with a chosen folder that has gone missing, the restore still succeeds and the Before restore backup is in `backups/`
- [X] T027 [P] [US2] Add to `tests/migrations/test_migrations.py`: restoring a backup whose database is at revision `base` (an empty schema created by running `alembic downgrade base` on a copy) upgrades the staged copy to head before swapping. Afterwards the live database's `current_revision == head_revision()` and the app serves `/customers`. Write it to cover any older revision added later
- [X] T028 [P] [US2] Write `tests/integration/test_recovery.py`:
  - **Garbage database**: write garbage over the first 100 bytes of `floorpro.db` before `create_app()`. Startup doesn't raise, `GET /healthz` → `200`, and `GET /customers` → `303` to `/recovery` (`HX-Redirect` for HTMX)
  - **Recovery screen**: shows the plain-English reason and the most recent backup
  - **Restore**: `POST /recovery/restore` restores it, moves the damaged `floorpro.db` (plus `-wal`/`-shm` if present) into `damaged/floorpro-<stamp>.db`, and sends you to `/` with the flash. Afterwards `/customers` works and `/recovery` → 404
  - **Start fresh**: `POST /recovery/start-fresh` with `confirm=START AGAIN` creates an empty database, keeps the damaged file, and shows the flash naming the damaged folder. A wrong confirmation → `422` "Type START AGAIN to confirm."
  - **No backups**: the recovery screen shows only **Start with no data** and **Restore from a file…**
  - **Legacy copy**: with no password set and only a legacy pre-upgrade `floorpro-*-pre-*.db`, `POST /recovery/restore` restores it
  - **Failed migration**: an Alembic failure during startup also enters recovery mode

### Implementation for User Story 2

- [X] T029 [US2] Add the restore pipeline to `src/floorpro/services/backup_service.py`, following research §8 steps 1–8. On every failure path, `tmp/restore-*.db` and any `restore-*.db-wal`/`-shm` are deleted and the live database is untouched. The staged copy is opened with `PRAGMA journal_mode=DELETE`:
  - **`open_backup(path) -> BackupInfo`**: header plus checks. An unknown `schema_revision` (not in `ScriptDirectory.walk_revisions()` and not `None`) → `BackupTooNew`
  - **`stage(path, password=None) -> Path`**: uses this computer's key when the key ids match. Otherwise it derives a key from `password` (`PasswordNeeded` if `None`, `WrongPassword` if the key id differs). Then it decrypts and decompresses into `tmp_dir()/restore-<random>.db`, checks `PRAGMA integrity_check == "ok"` and that the tables `alembic_version` and `business_settings` exist (else `BackupDamaged`), and runs `upgrade_to_head(staged, backup=False)` if the revision is older than head. Legacy plain `.db` files skip decryption
  - **`swap_in(staged, engine)`**: `engine.dispose()`, then `sqlite3.connect(staged).backup(sqlite3.connect(db_path, timeout=30))`, then `engine.dispose()` again
  - **`restore(path, engine, password=None) -> BackupInfo`**: acquire `LOCK`, call `stage`, then `make_backup(BackupKind.BEFORE_RESTORE)`, which always goes to `backups_dir()` (on failure raise `RestoreFailed` naming it), then `swap_in`, then remove the staged file and its `-wal`/`-shm`
- [X] T030 [US2] Create `src/floorpro/services/recovery_service.py`:
  - **`check_database(db_path) -> RecoveryInfo | None`**: open it and run `PRAGMA quick_check`. Any `sqlite3.DatabaseError` → a `RecoveryInfo` with the reason "FloorPro couldn't open your shop's data. It may have been damaged." and the detail logged
  - **`move_aside(db_path) -> Path`**: moves `floorpro.db`, `-wal` and `-shm` into `damaged_dir()` with a UTC stamp. It never deletes them
  - **`restore_in_recovery(path, password)`**: `stage`, then `move_aside`, then copy the staged database into a new `floorpro.db`. No Before restore backup, per research §13
  - **`start_fresh()`**: `move_aside`, then `upgrade_to_head` creates an empty database
- [X] T031 [US2] Update the lifespan in `src/floorpro/app.py` (makes T028 pass):
  - **Startup**: wrap the database check + `upgrade_to_head` + engine creation in recovery detection. On failure, set `app.state.recovery` and skip the engine. Otherwise set `app.state.recovery = None`
  - **Leaving recovery**: add a helper `app.state.reopen_database()` that builds a new engine and sessionmaker, runs `ensure_settings`, and clears recovery
  - **Middleware**: while in recovery, `load_settings` is skipped. A recovery middleware sends every path except `/static`, `/healthz` and `/recovery*` to `/recovery` (`303`, or `HX-Redirect` for HTMX)
  - **Startup clean-up**: call `backup_service.cleanup_partials()`
- [X] T032 [US2] Add `GET /backups/{loc}/{name}/restore` and `POST /backups/{loc}/{name}/restore` to `src/floorpro/routes/backups.py` per contracts/routes.md, using `parse_restore_confirm`:
  - **Errors**: `NotABackup`, `BackupDamaged`, `BackupTooNew`, `WrongPassword`, `RestoreFailed` and `BackupBusy` → `422` dialog with the exact message, returned into `#modal`
  - **Unprotected legacy copies**: `GET` shows the refusal "This older copy isn't protected. It can only be restored from the recovery screen." with no Restore button, and `POST` → `422` with data unchanged
  - **Success**: `HX-Redirect: /` + the flash cookie "Restored the backup from {created_at | local_datetime}"
  - **No session**: restore routes MUST NOT use `Depends(get_session)`. They call only `backup_service`
- [X] T033 [US2] Create `src/floorpro/routes/recovery.py` (`GET /recovery`, `POST /recovery/restore`, `POST /recovery/start-fresh`; every route → 404 when not in recovery) and register it in `app.py`. Create `src/floorpro/templates/recovery/index.html` as a standalone page that doesn't extend the nav layout and uses no `request.state.settings`. It reuses the shared button/field/card/table components, CSS and fonts. `recovery/_restore_form.html` holds the password field when needed. After success, call `app.state.reopen_database()` and redirect `303 /` with the flash. Recovery routes MUST NOT use `Depends(get_session)`; they call only `recovery_service`/`backup_service`. The **Restore this backup** and **Start with no data** buttons use `hx-indicator` with a "Restoring… this can take up to 30 seconds" (or "Starting…") spinner (CSS `.htmx-request` only) and `hx-disabled-elt="this"`
- [X] T034 [P] [US2] Create `src/floorpro/templates/backups/_confirm_restore.html`, a shared `modal` `<dialog>` with `aria-labelledby`:
  - **Details**: the backup's details as a definition list (date, type, customers, made by FloorPro {app_version})
  - **Warning**: callout text exactly "Everything changed since then will be replaced. FloorPro will first save a Before restore backup of your current data." and "Customers erased since this backup was made will come back and need erasing again."
  - **Fields**: the `confirm` field labelled "Type RESTORE to confirm", and an optional `password` field (`autocomplete="off"`)
  - **Refusal mode**: shows the refusal message and only a Close button
  - **Form**: posts to the action passed in, either `/backups/{loc}/{name}/restore` or `/backups/restore-file/confirm` with a hidden `source_token`, so US4 can reuse it
  - **Progress**: the Restore button uses `hx-indicator` with a "Restoring… this can take up to 30 seconds" spinner (CSS `.htmx-request` only, no new JS), plus `hx-disabled-elt="this"` so it can't be pressed twice
- [X] T035 [US2] Add a **Restore** action to each restorable row in `src/floorpro/templates/backups/_list.html`. It uses `hx-get` to the confirm dialog with `hx-target="#modal"`. There's no action for damaged rows or unprotected (legacy `.db`) rows, which can only be restored in recovery mode

**Checkpoint**: **MVP complete (US5 + US1 + US2)**. The constitution's release blocker is met
for the local computer.

---

## Phase 6: User Story 3 - Automatic backups (Priority: P2)

**Goal**: One automatic backup per day in the background, retention of 14, an on/off switch,
and a dashboard warning card.

**Independent Test**: With an injected clock, start the app on three simulated days and
confirm three automatic backups. With 16 automatic backups present, confirm only 14 remain,
and manual backups are never touched. Turn automatic backups off and see the dashboard
warning.

### Tests for User Story 3

- [X] T036 [P] [US3] Write `tests/integration/test_backups_auto.py`, using `sync_background` and a monkeypatched `backup_service.now()`:
  - **Once a day**: startup with a password set and `auto_enabled` makes one `automatic` backup and sets `last_auto_date` to today (local). A second startup the same day makes none. A startup the next day makes another. `GET /` also triggers it when the date has changed. Setting the first password (`POST /backups/password`) triggers the first automatic backup
  - **Retention**: with 15 automatic, 3 manual, 2 before-restore and 11 before-upgrade backups, the next automatic backup leaves 14 automatic, 3 manual, 2 before-restore and 10 before-upgrade (FR-018)
  - **Failure**: (monkeypatch `write_backup` to raise) → `last_auto_ok = false` with `last_auto_error` set, and the dashboard shows "The last automatic backup failed: …"
  - **Switch**: `POST /backups/automatic` without `auto_enabled` → toast "Automatic backups off", no automatic backup on the next day, and the dashboard shows "Automatic backups are off." With `auto_enabled=on` → toast "Automatic backups on"
  - **Startup time (SC-007)**: with the default background runner and a write slowed to 2 s, `create_app` startup returns in under 1 s
- [X] T037 [P] [US3] Write `tests/integration/test_dashboard_backups.py` covering the dashboard card:
  - **No password**: "Set a backup password to start backing up." linking to `/backups`
  - **Stale**: a last success 8 days old → "No backup in the last 7 days."
  - **No backups**: → "No backups yet."
  - **Healthy**: no warnings → the quiet line "Last backup: today at HH:MM"
  - **Speed**: the dashboard renders in under 300 ms with 40 backup files present (it doesn't scan files)

### Implementation for User Story 3

- [X] T038 [US3] Add the automatic-backup functions to `src/floorpro/services/backup_service.py`:
  - **`now()`**: an injectable clock
  - **`maybe_run_daily(app)`**: if `key_is_set()`, `prefs.auto_enabled` is true, and `prefs.last_auto_date != local today`, set `last_auto_date` immediately (so it runs only once even with concurrent triggers) and call `app.state.run_in_background(run_automatic)`
  - **`run_automatic()`**: `make_backup(AUTOMATIC)`, record `last_auto_ok`/`last_auto_error`, then `apply_retention()`. It catches and logs every exception and never raises
  - **`apply_retention()`**: deletes the files returned by `select_for_pruning(list_backups())`
  - **`set_auto_enabled(bool)`**
- [X] T039 [US3] Call `backup_service.maybe_run_daily(app)` at the end of a successful (non-recovery) lifespan startup in `src/floorpro/app.py`, and at the start of `GET /` in `src/floorpro/routes/dashboard.py`. Also call it after `POST /backups/password` succeeds in `src/floorpro/routes/backups.py` (US5 route)
- [X] T040 [US3] Add `POST /backups/automatic` to `src/floorpro/routes/backups.py`. Add the automatic on/off control to `src/floorpro/templates/backups/_panel.html` using the shared `checkbox` component in a small form that auto-submits with `hx-trigger="change"`. Include the description "Makes one backup each day you use FloorPro, and keeps the last 14."
- [X] T041 [US3] Add the backup card to `src/floorpro/templates/dashboard.html`. `routes/dashboard.py` passes `backup_status(load_prefs(), key_is_set(), now())` and `last_success_at`. Use the shared `card` component: warning styling with the messages and a "Go to Backups" button when there are warnings; otherwise the quiet "Last backup: …" line

**Checkpoint**: Shops that never press **Back up now** are protected and warned.

---

## Phase 7: User Story 4 - Keep a copy away from the computer, and move to a new computer (Priority: P2)

**Goal**: Choose a backup folder, fall back safely when it's missing, save copies anywhere,
and restore from any file, including from another computer, with that backup's password.

**Independent Test**: Choose a temporary folder, back up, and confirm the file is there. Make
the folder unreachable, run an automatic backup, and confirm it lands locally with the
fallback warning. Save a copy. Restore the committed fixture (made with a different password)
via **Restore from a file…**.

### Tests for User Story 4

- [X] T042 [P] [US4] Write `tests/integration/test_backups_files.py`:
  - **Choose a folder, desktop** (`fake_dialogs.choose_folder` → tmp folder): `POST /backups/folder/choose` → toast "Backups will be saved to {folder}". The next `POST /backups` writes there, and the panel shows the folder. Cancelled → `204`. A read-only folder → error toast
  - **Choose a folder, browser**: `POST /backups/folder` with a relative path, missing path or file path → `422` "Choose a folder FloorPro can save to." A valid path → saved
  - **Reset**: `POST /backups/folder/reset` → "Backups will be saved on this computer", and the folder's files are untouched
  - **Missing folder, manual backup**: (folder deleted) → error toast "The backup folder … can't be reached. Is the drive plugged in?" and nothing written
  - **Missing folder, automatic backup** → written to `backups/`, `last_fallback_at` set, and the dashboard shows "Your backup folder couldn't be reached, so backups were saved on this computer." The next successful folder backup clears it (FR-024)
  - **Save a copy, desktop**: `POST /backups/{loc}/{name}/save-copy` → a byte-identical copy at the chosen path + toast "Saved a copy to {path}". Cancelled → `204`
  - **Save a copy, browser**: `GET …/download` → `200` `application/octet-stream` with `Content-Disposition: attachment; filename="FloorPro-backup-….fpbackup"`
  - **Delete**: the dialog, then the `POST` deletes the file + toast "Backup deleted". For the most recent successful backup: `GET` shows the explanation, `POST` → `409`, and the file is kept (FR-021)
- [X] T043 [P] [US4] Write `tests/integration/test_backups_restore_file.py`:
  - **Desktop pick**: `POST /backups/restore-file/choose` with `fake_dialogs.open_file` → the fixture path renders the restore dialog with a `source_token` and a password field (the fixture's key id differs)
  - **Confirm, no password**: `POST /backups/restore-file/confirm` without a password → `422` "Enter the password this backup was made with."
  - **Confirm, wrong password**: → `422` "That password doesn't open this backup.", data unchanged
  - **Confirm, correct password**: `correct horse battery` → restored, with the data matching the fixture's known customers
  - **Upload**: `POST /backups/restore-file/upload` with the fixture (multipart) → the same dialog. A PDF upload → `422` "This file isn't a FloorPro backup, or it's damaged."
  - **Bad token**: a tampered `source_token` → `409` "That file is no longer available. Choose it again."
  - **Recovery**: the `/recovery/restore-file/*` equivalents work in recovery mode
- [X] T044 [P] [US4] Write `tests/integration/test_backup_fixture.py` (SC-006, runs on both macOS and Windows CI):
  - **Fixture**: `tests/fixtures/backup-v1.fpbackup` reads, decrypts with `correct horse battery`, and restores to a database with exactly the customers, settings and settings history listed in `tests/fixtures/README.md`
  - **This runner**: a backup made on this runner round-trips with an identical `db_dump`

### Implementation for User Story 4

- [X] T045 [US4] Create `scripts/make_backup_fixture.py`. It builds a fresh database at head in a temp folder with 3 known customers (one domestic, one trade, one archived) and one settings change, then writes `tests/fixtures/backup-v1.fpbackup` with the password `correct horse battery` and `KdfParams(n=1024, r=8, p=1, salt=<fresh 16 bytes>)`. It refuses to overwrite an existing fixture without `--force`. Run it once, commit the fixture, and list its contents in `tests/fixtures/README.md`
- [X] T046 [US4] Add the folder and file functions to `src/floorpro/services/backup_service.py`:
  - **`set_folder(path)`**: checks the path is absolute, exists, is a directory, and is writable (probe by creating and removing a `.FloorPro-probe` file; else `InvalidFolder("Choose a folder FloorPro can save to.")`). It saves `prefs.folder`
  - **`reset_folder()`**
  - **`current_destination()`**: unchanged
  - **`run_automatic` update**: on a folder `OSError`, write to `backups_dir()` instead and set `last_fallback_at`. A successful folder write clears it
  - **`save_copy(loc, name, dest)`**: uses `backup_file.atomic_copy`
  - **`delete_backup(loc, name)`**: raises `CannotDeleteLatest` for `most_recent`
  - **`make_source_token(path)` / `read_source_token(token)`**: HMAC-SHA256 with `paths.secret_key()` over the absolute path, base64url. `read_source_token` raises `LookupError` for a bad signature or a missing file
  - **`save_upload(file) -> Path`**: streams into `tmp_dir()`
- [X] T047 [US4] Add the folder and copy routes to `src/floorpro/routes/backups.py`:
  - **Folder**: `POST /backups/folder/choose`, `POST /backups/folder` and `POST /backups/folder/reset`
  - **Copy**: `POST /backups/{loc}/{name}/save-copy` (uses `app.state.dialogs.save_path`, else 404) and `GET /backups/{loc}/{name}/download` (`FileResponse`)
  - **Delete**: `GET /backups/{loc}/{name}/delete` and `POST /backups/{loc}/{name}/delete`
  - **Responses and messages**: exactly as in contracts/routes.md
- [X] T048 [US4] Add the restore-from-file routes to `src/floorpro/routes/backups.py` (`POST /backups/restore-file/choose`, `/upload` and `/confirm`) and to `src/floorpro/routes/recovery.py` (`/recovery/restore-file/choose`, `/upload` and `/confirm`). They reuse `backups/_confirm_restore.html` with `source_token`, and `restore()` / `restore_in_recovery()` with the given password. Like T032/T033, these routes MUST NOT use `Depends(get_session)`
- [X] T049 [P] [US4] Update the templates:
  - **`src/floorpro/templates/backups/_panel.html`**: the location section ("Saving to: …" with **Choose folder…** posting to `/backups/folder/choose` when dialogs exist, or a folder path `field` + Save posting to `/backups/folder` otherwise; plus "Use this computer" when a folder is set), **Restore from a file…** (desktop: a button posting to `/backups/restore-file/choose` with `hx-target="#modal"`; browser: a small multipart form with a labelled `<input type="file" accept=".fpbackup">`) and **Change password**
  - **`src/floorpro/templates/backups/_list.html`**: the **Save a copy to…** (desktop: post; browser: plain link with `hx-boost="false"` to `/download`) and **Delete** row actions. Delete is hidden for the most recent successful backup
  - **`src/floorpro/templates/backups/_confirm_delete.html`**: a `<dialog>` with `aria-labelledby`
  - **`src/floorpro/templates/recovery/index.html`**: the same restore-from-file controls, with the same `hx-indicator` "Restoring…" spinner and `hx-disabled-elt` on the confirm button

**Checkpoint**: All user stories are complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T050 [P] Write `tests/integration/test_backups_perf.py` (`@pytest.mark.slow`), seeding 10,000 customers with the existing perf-test helper:
  - **Back up now**: `POST /backups` completes in under 10 s (SC-001)
  - **Restore**: restore including the Before restore backup completes in under 30 s (SC-002)
  - **Backups page**: `GET /backups` with 40 backups renders in under 300 ms
- [X] T051 [P] Extend `tests/integration/test_accessibility.py`:
  - **Pages**: add `/backups` (no password, then with a password and backups listed), `/recovery` (in recovery mode) and the dashboard with the backup card to `test_pages_are_accessible`
  - **Dialogs**: add the restore, delete and change-password dialogs to `test_dialogs_are_accessible`
  - **Error states**: check password and confirm errors are linked with `aria-describedby`
  - **Progress**: the "Restoring…" and "Backing up…" spinner text is inside an `aria-live="polite"` region
- [X] T052 [P] Write `tests/unit/test_backup_logging.py`: after setting and changing the password, making a backup and a failed restore with a wrong password, the log file under `logs/` contains no password, no base64 key and no customer name (constitution: logging without exposing customer data)
- [X] T053 [P] Update `README.md`:
  - **What it does today**: add Backups (password-protected backups, Back up now, daily automatic backups that keep 14, chosen folder, Save a copy, Restore from a file, startup recovery)
  - **"Where the data lives"**: add `backup-key.json`, `backup-settings.json`, `backups/` (`.fpbackup`), `tmp/` and `damaged/`
  - **Warning**: forgetting the backup password means those backups can't be restored
- [X] T054 Check the PyInstaller compatibility of `cryptography`: add a short note under research §3 confirming PyInstaller's built-in hook, and that `backup_file` imports only `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. No packaging config yet (packaging is a later feature). Also add a unit test that monkeypatches `importlib.metadata.version` to raise `PackageNotFoundError` and confirms `floorpro.__version__` falls back to `"0.0.0+unknown"`
- [X] T055 Run the full quality gate:
  - `uv run ruff check .`, `uv run ruff format --check .` and `uv run pytest` (including slow tests) locally, and push
  - confirm the GitHub Actions run passes on macOS and Windows, including `test_backup_fixture.py`
- [ ] T056 Walk through `specs/002-backup-restore/quickstart.md` sections A–H in the pywebview window on macOS, fix anything found (with regression tests), and confirm the native folder, Save and Open dialogs work from the desktop window. Time a first-time restore from the Backups screen to the dashboard (target under 2 minutes, SC-005)

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: depends on Setup. Blocks all stories
- **US5 (Phase 3)**: depends on Foundational. **Blocks US1–US4**, because every backup needs the key
- **US1 (Phase 4)**: depends on US5
- **US2 (Phase 5)**: depends on US1 (`make_backup` is needed for the Before restore backup and for test data)
- **US3 (Phase 6)**: depends on US1. Independent of US2 and US4
- **US4 (Phase 7)**: depends on US1. The restore-from-file part depends on US2 (`restore`, `_confirm_restore.html`). Folder, copy and delete don't
- **Polish (Phase 8)**: after the stories you intend to ship (all of them, for a release)

```text
Setup → Foundational → US5 → US1 ─┬─→ US2 ──┬─→ US4 (restore from file)
                                  ├─→ US3   │
                                  └─→ US4 (folder, copy, delete) ─┘
                                                                  → Polish
```

### Within each story

- Write the tests first and watch them fail
- Then services, then routes, then templates
- Tasks touching `services/backup_service.py` or `routes/backups.py` run in sequence: they share a file

## Parallel Opportunities

- **Phase 1**: T002 and T003 in parallel (after T001)
- **Phase 2**: T004 ∥ T005 (tests). T007 ∥ T009 ∥ T010 alongside T006. T008 follows T006 and T007
- **US5**: T012 ∥ T013 ∥ T014 ∥ T018. Then T015 → T016 → T017
- **US1**: T019 ∥ T020 ∥ T023 ∥ T024. Then T021 → T022
- **US2**: T025 ∥ T026 ∥ T027 ∥ T028 ∥ T034. Then T029 → T030 → T031 → T032 → T033 → T035
- **After US1**: US3 and the folder/copy/delete part of US4 can proceed in parallel with US2 if staffed
- **Polish**: T050–T053 in parallel

### Parallel example: User Story 2

```text
Together: T025 test_backups_restore.py · T026 test_backups_restore_faults.py ·
          T027 migration test · T028 test_recovery.py · T034 _confirm_restore.html
Then in order: T029 restore pipeline → T030 recovery_service → T031 lifespan →
               T032 restore routes → T033 recovery routes → T035 list action
```

## Implementation Strategy

### MVP (US5 + US1 + US2)

1. Phases 1–2 (foundation)
2. Phase 3 (US5, password), Phase 4 (US1, back up now) and Phase 5 (US2, restore + recovery)
3. **Stop and validate**: quickstart A, B, C, G and H. This meets the constitution's backup and
   restore release blocker on a single computer

### Incremental delivery

4. **US3, automatic backups**: then validate quickstart D
5. **US4, folder, copies and another computer**: then validate quickstart E and F
6. **Polish**: performance, accessibility, logging, README and the CI gate on both OSes

### Suggested sessions (matching the earlier `/speckit-implement phase N` rhythm)

- **Phases 1 to 3**: setup, foundation, password
- **Phase 4**: back up now
- **Phase 5**: restore and recovery
- **Phase 6**: automatic backups
- **Phase 7**: folder, copies, restore from a file
- **Phase 8**: polish and walkthrough

## Notes

- Exact user-facing messages in these tasks come from research §15, data-model §4/§6 and the
  contracts. Tests assert them verbatim.
- Never log or echo passwords or keys (T052).
- No Alembic migration in this feature. If one turns out to be needed, it must come with a
  migration test (Principle III).
