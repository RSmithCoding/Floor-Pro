# Research: Backup and Restore

**Feature**: 002-backup-restore | **Date**: 2026-11-08

Each section records a decision, why it was made, and what else was considered. Section
numbers are referenced from [plan.md](plan.md), [data-model.md](data-model.md) and the
contracts.

## 1. What a backup contains

**Decision**: A backup is a complete, consistent copy of the SQLite database `floorpro.db`,
taken with SQLite's online backup API (`sqlite3.Connection.backup`, all pages in one step),
then compressed and encrypted into a single `.fpbackup` file.

**Rationale**: The database holds all shop data (FR-003), and features added later are covered
automatically, with no per-table export code to keep up to date. The backup API produces a
transactionally consistent snapshot while other connections keep reading and writing in WAL
mode (FR-004, US1-2). It is already used for the pre-migration copies in feature 001.

**Not in the backup**: `secret.key` (flash-cookie signing), logs, the backup key and backup
preferences (§5, §6). These belong to *this computer*, not to the shop's records.

**Alternatives considered**: a JSON/CSV export of each table (needs code per table, loses
exact types, slow for restore); copying the `.db` file directly (unsafe while WAL is active,
and misses uncheckpointed `-wal` contents); `VACUUM INTO` (also consistent, but the backup API
is already used and also serves the restore swap, §8).

## 2. File format

**Decision**: one binary file, `.fpbackup`, laid out as:

| Part | Content |
|------|---------|
| Magic | 16 bytes `FLOORPRO-BACKUP\x00` |
| Header length | 4-byte big-endian unsigned int |
| Header | UTF-8 JSON (see [contracts/backup-file.md](contracts/backup-file.md)): format version, kind, created time, app version, schema revision, contents summary, KDF parameters + salt, key id, nonce |
| Payload | AES-256-GCM ciphertext of the zlib-compressed database, followed by the 16-byte tag |

The header is plaintext so the Backups screen can list date, type, version and customer count
without the password. The magic, length and header bytes are passed to AES-GCM as associated
data, so any change to the header makes the file fail authentication. The header contains no
customer names, phones, emails or addresses (SC-008).

**Rationale**: a fixed, documented format that's byte-identical on macOS and Windows (no
paths, no line endings, explicit byte order: FR-016, SC-006). Authenticated encryption detects
both tampering and accidental damage (FR-013). Reading only the first few KB lists a backup.

**Size limit**: the payload is encrypted in one pass in memory. A shop database of several
hundred MB is fine on any shop PC. Chunked streaming encryption can be added later behind a
new `format_version`, if a shop ever gets near that.

**Alternatives considered**: encrypted ZIP (AES ZIP needs a third-party library, and the
listing metadata would sit in an unauthenticated directory); a plain `.db` with SQLCipher
(native build, hard to package with PyInstaller, and encrypts the live DB, which isn't
required); age/GPG (external tools).

## 3. Encryption and key derivation

**Decision**:
- **Cipher**: AES-256-GCM from the `cryptography` package, with a random 96-bit nonce per
  file.
- **Key derivation**: scrypt from the standard library (`hashlib.scrypt`), with
  `n=2**17, r=8, p=1` (about 128 MB of memory and 0.3 to 1 s on a typical shop PC), a random
  16-byte salt, and a 32-byte output. The parameters and salt are stored in every file header,
  so they can be raised later without breaking old backups.
- **Key id**: the first 16 bytes of `HMAC-SHA256(key, b"floorpro-backup-key-id")`. It's stored
  in the header to tell "this computer's current key" from "needs a password" without trying
  to decrypt anything.
- **Password text** is normalised to Unicode NFC before encoding as UTF-8, so the same typed
  password gives the same key on macOS and Windows.

**Wrong password vs damaged file**: if the key derived from the typed password doesn't
produce the header's key id → "That password doesn't open this backup." If the key id matches
but GCM authentication fails → the file is damaged (FR-013).

**Rationale**: AES-GCM is the standard authenticated cipher. `cryptography` ships wheels for
macOS (Intel and Apple Silicon) and Windows, and PyInstaller has built-in hooks for it. The
standard library has no AES, so one dependency is unavoidable for FR-026. Using stdlib scrypt
means only the cipher comes from the dependency.

**Packaging check** (T054): PyInstaller's bundled hooks (`pyinstaller-hooks-contrib`) cover
`cryptography`, including its Rust extension and OpenSSL. `backup_file` imports only
`cryptography.hazmat.primitives.ciphers.aead.AESGCM` and `cryptography.exceptions.InvalidTag`.
The dependency is capped below 49 (`cryptography>=48.0.1,<49`): release 48.0.1 is the last with
Intel macOS (`universal2`) wheels, and FloorPro must keep running on Intel Macs (macOS 12).
Revisit the cap when Intel Mac support is dropped, or build from source if a security fix
needs a newer release. No packaging configuration is added yet (packaging is a later feature).

**Alternatives considered**: PBKDF2 (weaker against GPU attacks at the same cost); Argon2
(needs a second dependency, `argon2-cffi`); a pure-Python AES (slow and unaudited); PyNaCl
(also native, no benefit over `cryptography`).

## 4. Remembering the key on this computer (FR-028)

**Decision**: when the password is set, FloorPro derives the key once and stores it in
`backup-key.json` in the data folder: KDF parameters, salt, key id and the derived key
(base64). The password itself is never stored, and nothing in the file can be turned back into
it. Backups and restores of this computer's own backups use the stored key directly, so no
password is asked for and no scrypt cost is paid per backup.

**Changing the password** (FR-030): the current password is checked by deriving a key with the
stored salt and comparing key ids (`hmac.compare_digest`). The new password gets a fresh salt
and key. The file is replaced atomically. Old backups keep their own salt and key id, so they
need the old password (US5-3).

**Threat model** (matches the spec's assumptions): the password protects backup files *away
from* this computer. Anyone who can use FloorPro on this computer can already read the live
database, so a key stored next to it adds no new exposure. The key file is outside `backups/`,
and never goes into a chosen backup folder.

**Alternatives considered**: the OS keychain via the `keyring` package (another dependency;
an unsigned macOS app triggers keychain prompts; no real gain without user accounts); asking
for the password on every backup (breaks automatic backups, US5-2); storing a password hash
only (can't encrypt new backups without the password).

## 5. Backup preferences live outside the database

**Decision**: preferences are kept in `backup-settings.json` in the data folder, not in
SQLite: automatic on/off, chosen folder, last success, last automatic run date and result,
last fallback. The file is written atomically (write a temp file, then `os.replace`).

**Rationale**: a restore replaces the whole database. If preferences lived in it, restoring an
old backup would silently switch automatic backups back on, forget the chosen folder, or wipe
the record of the last success. These settings describe this computer's setup, not the
shop's records. No Alembic migration is needed for this feature.

**Alternatives considered**: a table in `floorpro.db` that's excluded from restore (needs
special-case copying during the swap, and becomes stale in the backup copy).

## 6. Where backups are saved, names and atomic writes

**Locations**:
- **This computer**: `<data dir>/backups/`. It always holds "Before upgrade" copies (FR-031),
  holds all backups until a folder is chosen, and receives automatic-backup fallbacks
  (FR-024).
- **Chosen folder** (FR-022): any writable folder (USB drive, OneDrive, Dropbox, iCloud Drive).
  Manual and automatic backups go there once it's set. "Before restore" and "Before
  upgrade" backups always stay on this computer (§8, §11).

The Backups screen lists the `.fpbackup` files in both places (plus older pre-upgrade `.db`
files, §11). Each entry is identified by `(location, filename)`, where location is `local` or
`folder`. Filenames are checked against a strict pattern, and the path must resolve inside
that location, so nothing outside can be reached or deleted.

**Filename**: `FloorPro-backup-YYYY-MM-DD-HHMMSS-<kind>.fpbackup` in local time (readable when
browsing a USB stick), where kind is `manual`, `automatic`, `before-restore` or
`before-upgrade`. If that name already exists, `-2`, `-3`… is appended (edge case "two
backups in the same second"). The authoritative time and kind are in the header.

**Atomic write** (FR-005): write to `.FloorPro-<random>.partial` in the target folder, flush
and `fsync`, then `os.replace` to the final name. On any error the partial file is removed.
At startup, leftover `.partial` files older than a day are removed from both locations.

**Unavailable folder**: if the chosen folder is missing or not writable, a **manual** backup
fails with a plain-English message (US1-3, e.g. "The backup folder E:\Backups can't be
reached. Is the USB drive plugged in?"). An **automatic** backup falls back to the local
folder and records the fallback, which the dashboard card reports (FR-020, FR-024).

**Cloud folders**: syncing clients see a single complete file appear (thanks to the rename).
Files that the cloud client has moved off the disk may be downloaded when listed, because
listing reads each header. That's acceptable for a few dozen files.

## 7. Making a backup

**Steps** (`services/backup_service.make_backup(kind)`):
1. Take the process-wide backup lock (§10).
2. Snapshot `floorpro.db` into `<data dir>/tmp/` with the backup API.
3. Read the contents summary from the snapshot: `SELECT COUNT(*) FROM customer` (archived
   customers included). Later features register extra counts.
4. Read the schema revision from `alembic_version`.
5. Compress (zlib level 6), encrypt with the stored key, and write atomically (§6).
6. Delete the snapshot, record success or failure in preferences, then apply retention (§9).

**Performance** (SC-001): a 10,000-customer database is a few MB. The snapshot, compression and
encryption take well under a second. There's no scrypt cost, because the key is stored. A
slow-marked test checks the 10-second target.

**Progress** (edge case "very large data"): the button uses HTMX's request indicator. A
spinner and "Backing up…" appear while the request runs, via the `htmx-request` class. No
custom JavaScript.

## 8. Restoring

**Steps** (`restore(source, password=None)`), all before touching live data:
1. **Open**: check the magic and parse the header. Refuse a `format_version` newer than
   supported, or a schema revision this FloorPro doesn't know, with "This backup was made by a
   newer version of FloorPro. Update FloorPro first." (FR-014). Anything that isn't a FloorPro
   backup gets "This file isn't a FloorPro backup, or it's damaged." (FR-013).
2. **Key**: if the header's key id matches this computer's key, use it. Otherwise a password
   is required (FR-029, §3).
3. **Decrypt and decompress** into `<data dir>/tmp/restore-<random>.db`. GCM failure → damaged.
4. **Verify**: `PRAGMA integrity_check` is `ok`, and the `alembic_version` and
   `business_settings` tables exist.
5. **Upgrade the staged copy** if its revision is older than head: run Alembic on the
   *temporary* file (no pre-upgrade copy, because the backup file itself is the untouched
   original). A failure here leaves live data untouched.
6. **"Before restore" backup** of the current data (FR-011), written to `<data dir>/backups/`
   regardless of the chosen folder, so a missing USB drive can't block a restore. If it
   fails, stop.
7. **Swap**: dispose the SQLAlchemy engine's pooled connections, then copy the staged database
   into the live `floorpro.db` with the backup API (`staged.backup(live)`), using a 30-second
   busy timeout. SQLite writes the destination in one transaction, so it either completes or
   rolls back (FR-012). Dispose the pool again, so every new request reads the restored data
   (FR-015, no restart). The restore request itself MUST NOT hold a SQLAlchemy session or open
   transaction; otherwise the swap waits on its own lock.
8. Delete the staged file together with any `-wal`/`-shm` files beside it (the staged copy
   is opened with `journal_mode=DELETE` so normally there are none). Confirm with "Restored the backup from 3 Nov 2026, 17:30".

**Verified on this machine** (SQLite 3.53.1): restoring with the backup API into a live
WAL-mode database keeps it in WAL mode, passes `integrity_check`, and a connection that was
already open sees the restored contents straight away.

**Fault injection** (SC-004): tests flip bytes in the payload, truncate files, raise an error
during the swap, and make the destination read-only, then assert the live database's dump is
unchanged.

**Exactness** (SC-003): tests compare `iterdump()` of the original and restored databases.

**Alternatives considered**: closing everything and replacing `floorpro.db` with `os.replace`
(Windows refuses to replace a file another connection holds open, and the `-wal`/`-shm` files
would need handling too); restoring first and then migrating the live file (a failed migration
would leave live data changed).

## 9. Automatic backups and retention

**When** (FR-017): at startup, if automatic backups are on, a password is set, and no
automatic backup has run today (local date), FloorPro starts one in a background thread, so
opening the app isn't delayed (SC-007). The same check runs when the dashboard is opened. That
covers shops that leave FloorPro open overnight, and costs one comparison of dates.

**Background thread**: one short-lived `threading.Thread` per run, guarded by the backup lock.
This is not a worker pool or queue. It's recorded in Complexity Tracking (Principle VI). In
tests, `app.state.run_in_background` is replaced to run synchronously.

**Retention** (FR-018): after each automatic backup, the automatic backups in both locations
are sorted by header time, and all but the newest 14 are deleted. "Before upgrade" backups keep
their limit of 10 in the local folder. Manual and "Before restore" backups are never deleted
automatically. The selection is a pure function in `domain/backups.py`, tested first.

**Delete** (FR-021): users can delete any backup after confirming in a dialog, except the most
recent successful one (by header time, across both locations).

## 10. Concurrency

**Decision**: one process-wide `threading.Lock` in `backup_service` serialises make, restore,
delete and retention. If an automatic backup is running when **Back up now** or **Restore** is
pressed, the request waits up to 60 s for the lock, then reports "A backup is already in
progress. Try again in a moment." SQLite's own locking keeps normal page requests safe during
a snapshot. During the restore swap they wait on `busy_timeout` (5 s, already set), and the
swap of a typical database takes well under a second.

## 11. "Before upgrade" backups (FR-008, FR-031)

**Decision**: `migrate.backup_if_needed()` keeps working without a password, as now: a plain
`floorpro-<stamp>-pre-<rev>.db` copy in `backups/`. Once a backup key exists, it writes a
protected `.fpbackup` of kind `before_upgrade` instead. When the password is first set,
existing plain pre-upgrade `.db` files are converted to protected files, and the plain files
are deleted. These backups are only ever written to the local folder.

**Listing**: plain `.db` pre-upgrade files (only possible before a password is set) appear as
"Before upgrade · Not protected". They're listed only: they're converted to protected backups
when the password is first set. In recovery mode they can be restored (steps 4 to 8 of §8,
without decryption; no Before restore backup is needed there).

## 12. Native dialogs (choose folder, save a copy, restore from a file)

**Decision**: generalise feature 001's `app.state.save_file` hook into
`app.state.dialogs`, an object with three methods that return a path, or `None` if
cancelled:
- `save_path(filename)`, the Save dialog. It's used by **Save a copy to…** (the backup file is
  copied with `shutil.copyfile` to a `.partial`, then renamed) and by the existing customer
  export.
- `choose_folder()`, the folder picker (`FileDialog.FOLDER`), used to choose the backup
  folder.
- `open_file()`, the Open dialog (`FileDialog.OPEN`, filter
  `FloorPro backups (*.fpbackup)`), used by **Restore from a file…**.

`desktop.py` stays the only module that imports `webview`. pywebview marshals the dialogs onto
the GUI thread (verified for Save in feature 001).

**Browser mode / tests** (`--browser`, no pywebview): `dialogs` is `None`. The screens then
offer HTML equivalents: a text field for the folder path, a download link for **Save a copy
to…**, and `<input type="file">` upload for **Restore from a file…** (the upload is saved to
`<data dir>/tmp/` first). Integration tests also install a fake `dialogs` object to cover the
desktop paths.

**Restore-from-file token**: the picked or uploaded file's absolute path is put in a signed
token (HMAC with `paths.secret_key()`, as for the settings confirm in feature 001). The confirm
form posts the token back, so the server never trusts a path typed into the form.

## 13. Startup recovery (FR-025)

**Decision**: during startup, after Alembic, FloorPro opens the database and runs
`PRAGMA quick_check`. If opening, checking or migrating raises a SQLite or Alembic error, the
app starts in **recovery mode** instead of crashing. `app.state.recovery` holds the reason, and
middleware sends every page except `/static`, `/healthz` and `/recovery*` to `/recovery`.

**The recovery screen** explains in plain English that the shop's data couldn't be opened,
and offers:
1. **Restore the most recent backup** (newest by header time across both locations; asks for a
   password if its key isn't this computer's);
2. **Choose another backup** from the list, or **Restore from a file…**;
3. **Start with no data**, for when there is no backup at all. It's behind a typed
   confirmation.

Before any of these, the unreadable `floorpro.db` and its `-wal`/`-shm` files are moved to
`<data dir>/damaged/floorpro-<stamp>.db`. They're never deleted. No "Before restore" backup
is attempted, because the data can't be read; the moved-aside file serves that purpose. After a
successful restore, the app builds a new engine and leaves recovery mode without a restart.

**Cost**: `quick_check` on a 10,000-customer database takes a few milliseconds, well inside
SC-007's 1 s budget.

## 14. Dashboard backup card (FR-020)

**Decision**: a pure function `backup_status(prefs, key_set, now)` returns zero or more
warnings, in order: no password set ("Set a backup password to start backing up"); last
automatic backup failed; chosen folder unreachable (fallback used); automatic backups off; last
success more than 7 days ago (or never). The dashboard renders one shared `card` with these
messages and a link to `/backups`. It reads only `backup-settings.json` and checks whether the
key file exists, with no file scanning, so the dashboard stays under 300 ms.

## 15. Password rules (FR-027)

**Decision**:
- **Rules**: at least 10 characters after NFC normalisation, at most 1,024, not only spaces,
  and both entries must match.
- **Messages** (exact wording is a test fixture):
  - "Use at least 10 characters."
  - "Use at most 1,024 characters."
  - "The two passwords don't match."
  - "Enter your current backup password." (when changing)
  - "That isn't the current backup password." (when changing)
- **Form fields**: `type="password"`, with `autocomplete="new-password"` for new passwords and
  `"current-password"` for the current one. Passwords are never logged, echoed back into a
  form, or stored.

**Wording on the set-password screen**: "Write this password down and keep it somewhere safe,
away from this computer. If it's forgotten, backups made with it can never be restored, by
you or by anyone else."

## 16. Testing strategy

- **Unit, test-first** (`tests/unit/`):
  - file format round-trip
  - header tamper detection
  - payload damage and truncation
  - wrong password vs damaged file
  - key id
  - NFC normalisation
  - filename generation and collision suffixes
  - retention selection
  - "most recent successful" protection
  - `backup_status`
  - password rules
- **Integration** (`tests/integration/`): every route in
  [contracts/routes.md](contracts/routes.md), with a fake `dialogs` object for desktop paths
  and the HTML fallbacks for browser mode. It also covers making a backup while another session
  writes, restore exactness via `iterdump`, fault injection (SC-004), automatic backups
  (simulated days, injected clock), the dashboard card, and recovery mode with a corrupted
  database file.
- **Cross-platform** (SC-006): a small fixture backup with a known password,
  `tests/fixtures/backup-v1.fpbackup` made by `scripts/make_backup_fixture.py`, is committed
  and restored by tests on both macOS and Windows CI. A test also checks that a backup written
  on the CI runner can be read back.
- **Privacy** (SC-008): a test creates customers with distinctive names, phones, emails and
  addresses, makes a backup, and checks that none of those strings appear in the file bytes
  (in UTF-8 or UTF-16).
- **Performance** (`@pytest.mark.slow`): 10,000 customers, back up in under 10 s, restore in
  under 30 s.
- **Migrations**: restoring a backup at an older revision upgrades it. With only `0001` today,
  the test uses a database at `base` (an empty schema). The test is written so it covers real
  older revisions as they're added.
- **scrypt cost in tests**: tests pass small KDF parameters (`n=2**10`) through a module
  setting, and one test checks that the production defaults are used when nothing is
  overridden.

## 17. Known consequence: erased customers and old backups

Restoring a backup made before a customer was erased (feature 001, FR-021) brings that
customer back. Under UK GDPR guidance this is acceptable if backups aren't used for anything
else and erasure is re-applied after a restore. This feature doesn't track erasures outside
the database. The restore confirmation adds: "Customers erased since this backup was made will
come back and need erasing again." Automatically re-applying erasures can be a later
improvement.
