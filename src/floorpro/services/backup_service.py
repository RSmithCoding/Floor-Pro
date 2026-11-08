"""Backups: the key and preference stores, listing, making, restoring and housekeeping.

Rules live in ``floorpro.domain.backups`` and the file format in ``floorpro.backup_file``;
this module does the I/O and orchestration (research.md §4–§12).
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from floorpro import backup_file, paths
from floorpro.backup_file import BackupError, KdfParams
from floorpro.domain.backups import BackupInfo, BackupKind, BackupPrefs, parse_filename

log = logging.getLogger(__name__)

LOCK = threading.Lock()
LOCK_TIMEOUT = 60.0
PARTIAL_MAX_AGE = 24 * 60 * 60


# --- Errors ----------------------------------------------------------------------------------


class BackupBusy(BackupError):
    message = "A backup is already in progress. Try again in a moment."


class NoPassword(BackupError):
    message = "Set a backup password first."


class BackupFailed(BackupError):
    message = "The backup couldn't be saved."


class PasswordAlreadySet(BackupError):
    message = "A backup password is already set."


class PasswordNeeded(BackupError):
    message = "Enter the password this backup was made with."


class RestoreFailed(BackupError):
    message = "The restore couldn't be completed. Your current data hasn't been changed."


class InvalidFolder(BackupError):
    message = "Choose a folder FloorPro can save to."


class CannotDeleteLatest(BackupError):
    message = "This is your most recent backup, so it can't be deleted."


# --- Clock and lock --------------------------------------------------------------------------


def now() -> datetime:
    """Current UTC time. Tests monkeypatch this to simulate days passing."""
    return datetime.now(UTC)


def local_now() -> datetime:
    return now().astimezone()


@contextlib.contextmanager
def acquire(timeout: float | None = None) -> Iterator[None]:
    """Serialise backup work (make, restore, delete, retention) across threads."""
    if not LOCK.acquire(timeout=LOCK_TIMEOUT if timeout is None else timeout):
        raise BackupBusy()
    try:
        yield
    finally:
        LOCK.release()


# --- Preferences (backup-settings.json) ------------------------------------------------------

_DATETIME_PREFS = {"last_success_at", "last_fallback_at"}


def load_prefs() -> BackupPrefs:
    path = paths.backup_prefs_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
        known = {f.name for f in fields(BackupPrefs)}
        values: dict[str, Any] = {}
        for name, value in data.items():
            if name not in known:
                continue
            if name in _DATETIME_PREFS and value is not None:
                value = datetime.fromisoformat(value)
            values[name] = value
        return BackupPrefs(**values)
    except FileNotFoundError:
        return BackupPrefs()
    except (ValueError, TypeError) as exc:
        log.warning("Backup preferences unreadable (%s); using defaults", type(exc).__name__)
        return BackupPrefs()


def save_prefs(prefs: BackupPrefs) -> None:
    data = asdict(prefs)
    for name in _DATETIME_PREFS:
        if data[name] is not None:
            data[name] = data[name].isoformat()
    payload = json.dumps(data, indent=2).encode("utf-8")
    backup_file.atomic_write_bytes(paths.backup_prefs_path(), payload)


def update_prefs(**changes: Any) -> BackupPrefs:
    prefs = load_prefs()
    for name, value in changes.items():
        setattr(prefs, name, value)
    save_prefs(prefs)
    return prefs


# --- Key (backup-key.json) -------------------------------------------------------------------


@dataclass(frozen=True)
class StoredKey:
    kdf: KdfParams
    key: bytes
    key_id: bytes
    set_at: datetime


def load_key() -> StoredKey | None:
    path = paths.backup_key_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        kdf = KdfParams.from_header(data["kdf"])
        key = base64.b64decode(data["key"], validate=True)
        kid = base64.b64decode(data["key_id"], validate=True)
        if data.get("version") != 1 or len(key) != 32 or backup_file.key_id(key) != kid:
            raise ValueError("inconsistent key file")
        return StoredKey(kdf, key, kid, datetime.fromisoformat(data["set_at"]))
    except FileNotFoundError:
        return None
    except (ValueError, TypeError, KeyError, BackupError) as exc:
        log.warning("Backup key file is invalid (%s); treating as not set", type(exc).__name__)
        return None


def key_is_set() -> bool:
    return load_key() is not None


def current_key_id() -> bytes | None:
    stored = load_key()
    return stored.key_id if stored else None


def _save_key(kdf: KdfParams, key: bytes) -> StoredKey:
    stored = StoredKey(kdf, key, backup_file.key_id(key), now())
    data = {
        "version": 1,
        "kdf": kdf.to_header(),
        "key": base64.b64encode(key).decode("ascii"),
        "key_id": base64.b64encode(stored.key_id).decode("ascii"),
        "set_at": stored.set_at.isoformat(),
    }
    backup_file.atomic_write_bytes(
        paths.backup_key_path(), json.dumps(data, indent=2).encode("utf-8")
    )
    return stored


# --- Locations and listing -------------------------------------------------------------------


@dataclass(frozen=True)
class Location:
    name: str  # "local" | "folder"
    path: Path
    reachable: bool


def locations() -> list[Location]:
    result = [Location("local", paths.backups_dir(), True)]
    folder = load_prefs().folder
    if folder:
        path = Path(folder)
        result.append(Location("folder", path, path.is_dir()))
    return result


def current_destination() -> Path:
    """Where manual and automatic backups go: the chosen folder if set, else this computer."""
    folder = load_prefs().folder
    return Path(folder) if folder else paths.backups_dir()


def resolve(loc: str, name: str) -> Path:
    """The path of a listed backup. Raises LookupError for anything else (→ 404)."""
    parsed = parse_filename(name)
    if parsed is None:
        raise LookupError(name)
    if parsed.legacy and loc != "local":
        raise LookupError(name)
    for location in locations():
        if location.name == loc:
            base = location.path.resolve()
            path = (location.path / name).resolve()
            if path.parent != base or not path.is_file():
                raise LookupError(name)
            return path
    raise LookupError(loc)


def read_info(path: Path, location: str) -> BackupInfo:
    """Describe one backup file from its header (or, for legacy copies, the name and DB)."""
    parsed = parse_filename(path.name)
    size = path.stat().st_size
    if parsed is not None and parsed.legacy:
        revision, customers = _inspect_plain_db(path)
        return BackupInfo(
            location=location,
            filename=path.name,
            kind=BackupKind.BEFORE_UPGRADE,
            created_at=parsed.created_at,
            app_version="",
            schema_revision=revision,
            contents={"customers": customers} if customers is not None else {},
            size_bytes=size,
            protected=False,
            key_id=None,
            damaged=customers is None,
        )
    try:
        header = backup_file.read_header(path)
        created = datetime.fromisoformat(header["created_at"].replace("Z", "+00:00"))
        return BackupInfo(
            location=location,
            filename=path.name,
            kind=BackupKind(header["kind"]),
            created_at=created,
            app_version=str(header["app_version"]),
            schema_revision=header["schema_revision"],
            contents={k: int(v) for k, v in header["contents"].items()},
            size_bytes=size,
            protected=True,
            key_id=backup_file.header_key_id(header),
        )
    except (BackupError, ValueError, TypeError, AttributeError):
        return BackupInfo(
            location=location,
            filename=path.name,
            kind=None,
            created_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
            app_version="",
            schema_revision=None,
            contents={},
            size_bytes=size,
            protected=True,
            key_id=None,
            damaged=True,
        )


def _inspect_plain_db(path: Path) -> tuple[str | None, int | None]:
    """(revision, customers) of a plain database file; customers is None if unreadable."""
    import sqlite3

    try:
        revision, customers = _summary(path, read_only=True)
        return revision, customers
    except sqlite3.Error:
        return None, None


def list_backups() -> list[BackupInfo]:
    """Every backup in both locations, newest first."""
    backups: list[BackupInfo] = []
    for location in locations():
        if not location.reachable:
            continue
        try:
            entries = list(location.path.iterdir())
        except OSError:
            log.warning("Backup location %s could not be listed", location.name)
            continue
        for entry in entries:
            parsed = parse_filename(entry.name)
            if parsed is None or (parsed.legacy and location.name != "local"):
                continue
            try:
                if entry.is_file():
                    backups.append(read_info(entry, location.name))
            except OSError:
                continue
    backups.sort(key=lambda b: b.created_at, reverse=True)
    backups.sort(key=lambda b: b.damaged)  # stable: damaged files last, valid newest first
    return backups


def cleanup_partials() -> None:
    """Remove stale partial files from both locations and empty the scratch folder."""
    cutoff = time.time() - PARTIAL_MAX_AGE
    for location in locations():
        if not location.reachable:
            continue
        with contextlib.suppress(OSError):
            for partial in location.path.glob(".FloorPro-*.partial"):
                with contextlib.suppress(OSError):
                    if partial.stat().st_mtime < cutoff:
                        partial.unlink()
    for leftover in paths.tmp_dir().iterdir():
        with contextlib.suppress(OSError):
            if leftover.is_file():
                leftover.unlink()


# --- Password (US5) --------------------------------------------------------------------------


def set_password(password: str) -> StoredKey:
    """Set the first backup password: store the derived key, then protect legacy copies."""
    if key_is_set():
        raise PasswordAlreadySet()
    kdf = backup_file.new_kdf()
    stored = _save_key(kdf, backup_file.derive_key(password, kdf))
    log.info("Backup password set")
    protect_legacy_upgrade_copies()
    return stored


def check_current_password(password: str) -> bool:
    import hmac

    stored = load_key()
    if stored is None or not password:
        return False
    candidate = backup_file.key_id(backup_file.derive_key(password, stored.kdf))
    return hmac.compare_digest(candidate, stored.key_id)


def change_password(current: str, new: str) -> StoredKey:
    """Replace the key. Backups already made keep needing the password they were made with."""
    if not check_current_password(current):
        raise backup_file.WrongPassword("That isn't the current backup password.")
    kdf = backup_file.new_kdf()
    stored = _save_key(kdf, backup_file.derive_key(new, kdf))
    log.info("Backup password changed")
    return stored


def _iso_z(when: datetime) -> str:
    return when.astimezone(UTC).isoformat().replace("+00:00", "Z")


def protect_legacy_upgrade_copies() -> int:
    """Convert feature 001's plain pre-upgrade copies into protected backups."""
    from floorpro import __version__
    from floorpro.domain.backups import filename_for

    stored = load_key()
    if stored is None:
        return 0
    folder = paths.backups_dir()
    converted = 0
    with acquire():
        for plain in sorted(folder.glob("floorpro-*-pre-*.db")):
            parsed = parse_filename(plain.name)
            if parsed is None or not parsed.legacy:
                continue
            revision, customers = _inspect_plain_db(plain)
            if customers is None:
                log.warning("Pre-upgrade copy %s is unreadable; left as it is", plain.name)
                continue
            fields = {
                "kind": BackupKind.BEFORE_UPGRADE.value,
                "created_at": _iso_z(parsed.created_at),
                "app_version": __version__,
                "schema_revision": revision,
                "contents": {"customers": customers},
            }
            existing = {p.name for p in folder.iterdir()}
            local = parsed.created_at.astimezone().replace(tzinfo=None)
            name = filename_for(BackupKind.BEFORE_UPGRADE, local, existing)
            backup_file.write_backup(
                folder, name, plain.read_bytes(), fields, stored.key, stored.kdf
            )
            plain.unlink()
            converted += 1
    if converted:
        log.info("Protected %d pre-upgrade copies", converted)
    return converted


# --- Snapshots and writing -------------------------------------------------------------------


def _summary(db: Path, read_only: bool = False) -> tuple[str | None, int]:
    """(schema revision, customer count) of a database snapshot."""
    import sqlite3

    conn = (
        sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
        if read_only
        else sqlite3.connect(db)
    )
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
        revision = None
        if "alembic_version" in tables:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            revision = row[0] if row else None
        customers = 0
        if "customer" in tables:
            customers = int(conn.execute("SELECT COUNT(*) FROM customer").fetchone()[0])
        return revision, customers
    finally:
        conn.close()


def remove_db_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        with contextlib.suppress(OSError):
            Path(f"{path}{suffix}").unlink()


def snapshot(db_path: Path) -> tuple[bytes, str | None, int]:
    """A consistent copy of the live database, taken with SQLite's backup API (research §1)."""
    import secrets
    import sqlite3

    target = paths.tmp_dir() / f"snapshot-{secrets.token_hex(6)}.db"
    try:
        source = sqlite3.connect(db_path, timeout=30)
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        revision, customers = _summary(target)
        return target.read_bytes(), revision, customers
    finally:
        remove_db_files(target)


def write_protected(
    kind: BackupKind,
    db_bytes: bytes,
    revision: str | None,
    customers: int,
    folder: Path,
    stored: StoredKey,
) -> Path:
    from floorpro import __version__
    from floorpro.domain.backups import filename_for

    fields = {
        "kind": kind.value,
        "created_at": _iso_z(now()),
        "app_version": __version__,
        "schema_revision": revision,
        "contents": {"customers": customers},
    }
    existing = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
    name = filename_for(kind, local_now().replace(tzinfo=None), existing)
    return backup_file.write_backup(folder, name, db_bytes, fields, stored.key, stored.kdf)


def write_before_upgrade(db_path: Path) -> Path | None:
    """Called by migrate before an upgrade once a password is set. Always local; keeps 10."""
    from floorpro.domain.backups import KEEP_BEFORE_UPGRADE

    stored = load_key()
    if stored is None:
        return None
    with acquire():
        data, revision, customers = snapshot(db_path)
        path = write_protected(
            BackupKind.BEFORE_UPGRADE, data, revision, customers, paths.backups_dir(), stored
        )
        upgrades = [
            b
            for b in list_backups()
            if b.location == "local" and b.kind is BackupKind.BEFORE_UPGRADE and b.protected
        ]
        for old in upgrades[KEEP_BEFORE_UPGRADE:]:
            with contextlib.suppress(OSError):
                (paths.backups_dir() / old.filename).unlink()
    log.info("Protected backup %s written before upgrading", path.name)
    return path


# --- Making a backup (US1) -------------------------------------------------------------------


def _failure_message(exc: OSError, folder: Path) -> str:
    import errno

    if exc.errno == errno.ENOSPC:
        return "There isn't enough space to save the backup."
    if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return f"FloorPro isn't allowed to save in {folder}."
    if exc.errno == errno.ENOENT or not folder.is_dir():
        return f"The backup folder {folder} can't be reached. Is the drive plugged in?"
    return "The backup couldn't be saved."


LOCAL_ONLY = {BackupKind.BEFORE_RESTORE, BackupKind.BEFORE_UPGRADE}


def make_backup(
    kind: BackupKind, destination: Path | None = None, *, locked: bool = False
) -> BackupInfo:
    """Snapshot, compress, encrypt and write a backup (research §7).

    Before restore and Before upgrade backups always go to this computer. ``locked`` is set
    by callers that already hold the backup lock (restore).
    """
    stored = load_key()
    if stored is None:
        raise NoPassword()
    if destination is None:
        destination = paths.backups_dir() if kind in LOCAL_ONLY else current_destination()
    lock = contextlib.nullcontext() if locked else acquire()
    with lock:
        try:
            data, revision, customers = snapshot(paths.db_path())
            path = write_protected(kind, data, revision, customers, destination, stored)
        except OSError as exc:
            log.warning("Backup (%s) to %s failed: %s", kind.value, destination, exc)
            raise BackupFailed(_failure_message(exc, destination)) from exc
        changes: dict[str, Any] = {}
        if kind is not BackupKind.BEFORE_UPGRADE:
            changes["last_success_at"] = now()
        folder = load_prefs().folder
        if folder and destination.resolve() == Path(folder).resolve():
            changes["last_fallback_at"] = None  # the folder is back (FR-024)
        if changes:
            update_prefs(**changes)
    log.info("Backup written: %s (%d bytes)", path.name, path.stat().st_size)
    is_local = destination.resolve() == paths.backups_dir().resolve()
    return read_info(path, "local" if is_local else "folder")


# --- Restoring (US2) -------------------------------------------------------------------------

REQUIRED_TABLES_BEFORE_UPGRADE = {"alembic_version"}
REQUIRED_TABLES = {"alembic_version", "business_settings"}


def known_revisions() -> set[str]:
    from alembic.script import ScriptDirectory

    from floorpro.migrate import alembic_config

    script = ScriptDirectory.from_config(alembic_config())
    return {rev.revision for rev in script.walk_revisions()}


def check_revision(revision: str | None) -> None:
    """Refuse backups from a newer FloorPro (a schema revision this version doesn't know)."""
    if revision is not None and revision not in known_revisions():
        raise backup_file.BackupTooNew()


def open_backup(path: Path) -> BackupInfo:
    """Describe a backup and check it can be restored by this FloorPro version."""
    info = read_info(path, "file")
    if info.damaged:
        raise backup_file.NotABackup()
    if info.protected:
        backup_file.read_header(path)  # raises the precise error (e.g. BackupTooNew)
    check_revision(info.schema_revision)
    return info


def _is_plain_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _tables(conn) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _verify_staged(staged: Path) -> str | None:
    """Integrity and shape checks on the staged copy; returns its schema revision."""
    import sqlite3

    try:
        conn = sqlite3.connect(staged)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise backup_file.BackupDamaged()
            if not _tables(conn) >= REQUIRED_TABLES_BEFORE_UPGRADE:
                raise backup_file.BackupDamaged()
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise backup_file.BackupDamaged() from exc


def _check_required_tables(staged: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(staged)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        if not _tables(conn) >= REQUIRED_TABLES:
            raise backup_file.BackupDamaged()
    finally:
        conn.close()


def stage(path: Path, password: str | None = None) -> Path:
    """Decrypt, check and (if older) upgrade a backup into tmp/ without touching live data."""
    import secrets

    from floorpro.migrate import head_revision, upgrade_to_head

    staged = paths.tmp_dir() / f"restore-{secrets.token_hex(6)}.db"
    try:
        parsed = parse_filename(path.name)
        if (parsed is not None and parsed.legacy) or _is_plain_sqlite(path):
            staged.write_bytes(path.read_bytes())
        else:
            header = backup_file.read_header(path)
            check_revision(header["schema_revision"])
            stored = load_key()
            if stored is not None and stored.key_id == backup_file.header_key_id(header):
                key = stored.key
            elif not password:
                raise PasswordNeeded()
            else:
                kdf = KdfParams.from_header(header["kdf"])
                key = backup_file.derive_key(password, kdf)
            staged.write_bytes(backup_file.decrypt(path, key))
        revision = _verify_staged(staged)
        check_revision(revision)
        if revision != head_revision():
            try:
                upgrade_to_head(staged, backup=False)
            except Exception as exc:
                log.exception("Upgrading a staged backup failed")
                raise RestoreFailed(
                    "This backup couldn't be upgraded to this version of FloorPro. "
                    "Your current data hasn't been changed."
                ) from exc
        _check_required_tables(staged)
        return staged
    except BaseException:
        remove_db_files(staged)
        raise


def copy_database(source: Path, dest: Path) -> None:
    """Copy one database into another in a single transaction (SQLite backup API)."""
    import sqlite3

    src = sqlite3.connect(source)
    dst = sqlite3.connect(dest, timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def swap_in(staged: Path, engine) -> None:
    """Replace the live data with the staged copy, all-or-nothing (FR-012, research §8)."""
    if engine is not None:
        engine.dispose()
    try:
        copy_database(staged, paths.db_path())
    finally:
        if engine is not None:
            engine.dispose()


def restore(path: Path, engine, password: str | None = None) -> BackupInfo:
    """Restore a backup over the live data, after making a Before restore backup."""
    import sqlite3

    info = open_backup(path)
    with acquire():
        staged = stage(path, password)
        try:
            try:
                make_backup(BackupKind.BEFORE_RESTORE, locked=True)
            except BackupError as exc:
                raise RestoreFailed(
                    "FloorPro couldn't save a Before restore backup first, so nothing was "
                    f"restored. {exc.message}"
                ) from exc
            try:
                swap_in(staged, engine)
            except sqlite3.Error as exc:
                log.exception("Restore swap failed")
                raise RestoreFailed() from exc
        finally:
            remove_db_files(staged)
    log.info("Restored backup %s", path.name)
    return info


# --- Automatic backups and retention (US3) ---------------------------------------------------

_DAILY_LOCK = threading.Lock()


def maybe_run_daily(app) -> bool:
    """Start today's automatic backup in the background if it's due (research §9)."""
    if getattr(app.state, "recovery", None) is not None or not key_is_set():
        return False
    today = local_now().date().isoformat()
    with _DAILY_LOCK:
        prefs = load_prefs()
        if not prefs.auto_enabled or prefs.last_auto_date == today:
            return False
        update_prefs(last_auto_date=today)  # claim today first, so it only runs once
    app.state.run_in_background(run_automatic)
    return True


def run_automatic() -> None:
    """Make the automatic backup, falling back to this computer if the folder is missing.

    Runs in a background thread: it records the outcome and never raises.
    """
    try:
        folder = load_prefs().folder
        try:
            make_backup(BackupKind.AUTOMATIC)
            fallback = None
        except BackupFailed:
            if not folder:
                raise
            log.warning("Backup folder unavailable; saving the automatic backup locally")
            make_backup(BackupKind.AUTOMATIC, destination=paths.backups_dir())
            fallback = now()
        update_prefs(last_auto_ok=True, last_auto_error=None, last_fallback_at=fallback)
        apply_retention()
    except BackupError as exc:
        update_prefs(last_auto_ok=False, last_auto_error=exc.message)
    except Exception:
        log.exception("Automatic backup failed")
        update_prefs(last_auto_ok=False, last_auto_error="The backup couldn't be saved.")


def apply_retention() -> int:
    """Delete automatic backups beyond 14 and Before upgrade beyond 10 (FR-018)."""
    from floorpro.domain.backups import most_recent, select_for_pruning

    removed = 0
    with acquire():
        backups = list_backups()
        latest = most_recent(backups)
        for backup in select_for_pruning(backups):
            if backup is latest:
                continue
            try:
                resolve(backup.location, backup.filename).unlink()
                removed += 1
            except (LookupError, OSError):
                log.warning("Couldn't remove old backup %s", backup.filename)
    if removed:
        log.info("Retention removed %d old backups", removed)
    return removed


def set_auto_enabled(enabled: bool) -> None:
    update_prefs(auto_enabled=enabled)


# --- Folder, copies, delete and restore-from-file (US4) --------------------------------------


def set_folder(path: Path | str) -> Path:
    """Choose the backup folder after checking FloorPro can write there."""
    folder = Path(path)
    if not str(path).strip() or not folder.is_absolute() or not folder.is_dir():
        raise InvalidFolder()
    probe = folder / ".FloorPro-probe"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as exc:
        raise InvalidFolder() from exc
    update_prefs(folder=str(folder), last_fallback_at=None)
    log.info("Backup folder chosen")
    return folder


def reset_folder() -> None:
    update_prefs(folder=None, last_fallback_at=None)


def save_copy(loc: str, name: str, dest: Path) -> Path:
    return backup_file.atomic_copy(resolve(loc, name), Path(dest))


def delete_backup(loc: str, name: str) -> None:
    from floorpro.domain.backups import most_recent

    path = resolve(loc, name)
    with acquire():
        latest = most_recent(list_backups())
        if latest is not None and (latest.location, latest.filename) == (loc, name):
            raise CannotDeleteLatest()
        path.unlink()
    log.info("Backup deleted: %s", name)


def _token_sig(payload: bytes) -> str:
    import hashlib
    import hmac

    return hmac.new(paths.secret_key(), b"restore-file:" + payload, hashlib.sha256).hexdigest()


def make_source_token(path: Path) -> str:
    """A signed reference to a picked or uploaded file, so the form never carries a raw path."""
    payload = base64.urlsafe_b64encode(str(Path(path).resolve()).encode("utf-8"))
    return f"{payload.decode('ascii')}.{_token_sig(payload)}"


def read_source_token(token: str) -> Path:
    import hmac

    try:
        payload, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(_token_sig(payload.encode("ascii")), signature):
            raise LookupError("bad signature")
        path = Path(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise LookupError("bad token") from exc
    if not path.is_file():
        raise LookupError("file gone")
    return path


def save_upload(fileobj) -> Path:
    """Stream an uploaded file into tmp/ (browser mode's Restore from a file)."""
    import secrets
    import shutil

    target = paths.tmp_dir() / f"upload-{secrets.token_hex(8)}.fpbackup"
    with open(target, "wb") as out:
        shutil.copyfileobj(fileobj, out, 1024 * 1024)
    return target


def discard_upload(path: Path) -> None:
    """Remove an uploaded file once it has been restored (never a user's own file)."""
    with contextlib.suppress(OSError):
        if path.resolve().parent == paths.tmp_dir().resolve():
            path.unlink()
