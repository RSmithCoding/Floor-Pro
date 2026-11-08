"""Pure backup rules: kinds, file names, retention, dashboard status and password checks.

No I/O here; see data-model.md §1, §3, §4 and §6 for the rules.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

KEEP_AUTOMATIC = 14
KEEP_BEFORE_UPGRADE = 10
STALE_AFTER = timedelta(days=7)
MIN_PASSWORD = 10
MAX_PASSWORD = 1024


class BackupKind(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    BEFORE_RESTORE = "before_restore"
    BEFORE_UPGRADE = "before_upgrade"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").capitalize()

    @property
    def slug(self) -> str:
        """The form used in file names: ``before-restore``."""
        return self.value.replace("_", "-")

    @classmethod
    def from_slug(cls, slug: str) -> BackupKind:
        return cls(slug.replace("-", "_"))


# --- File names ------------------------------------------------------------------------------

FILENAME_RE = re.compile(
    r"^FloorPro-backup-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})-"
    r"(manual|automatic|before-restore|before-upgrade)(?:-(\d+))?\.fpbackup$"
)
LEGACY_RE = re.compile(r"^floorpro-(\d{8}T\d{12}Z)-pre-[0-9a-z_]+\.db$")


@dataclass(frozen=True)
class ParsedName:
    kind: BackupKind
    legacy: bool
    created_at: datetime  # local naive time for new names, aware UTC for legacy names


def filename_for(kind: BackupKind, local_dt: datetime, existing_names: set[str]) -> str:
    base = f"FloorPro-backup-{local_dt:%Y-%m-%d-%H%M%S}-{kind.slug}"
    name = f"{base}.fpbackup"
    counter = 2
    while name in existing_names:
        name = f"{base}-{counter}.fpbackup"
        counter += 1
    return name


def parse_filename(name: str) -> ParsedName | None:
    if match := FILENAME_RE.fullmatch(name):
        y, mo, day, h, mi, s, slug, _ = match.groups()
        try:
            when = datetime(int(y), int(mo), int(day), int(h), int(mi), int(s))
        except ValueError:
            return None
        return ParsedName(BackupKind.from_slug(slug), False, when)
    if match := LEGACY_RE.fullmatch(name):
        try:
            when = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
        except ValueError:
            return None
        return ParsedName(BackupKind.BEFORE_UPGRADE, True, when)
    return None


# --- Backups ---------------------------------------------------------------------------------


@dataclass
class BackupInfo:
    location: str  # "local" | "folder"
    filename: str
    kind: BackupKind | None  # None when damaged
    created_at: datetime
    app_version: str
    schema_revision: str | None
    contents: dict[str, int]
    size_bytes: int
    protected: bool
    key_id: bytes | None
    damaged: bool = False

    @property
    def customers(self) -> int:
        return int(self.contents.get("customers", 0))

    @property
    def restorable(self) -> bool:
        """Restorable from the Backups screen (legacy plain copies only in recovery mode)."""
        return not self.damaged and self.protected

    def needs_password(self, current_key_id: bytes | None) -> bool:
        return self.protected and (current_key_id is None or self.key_id != current_key_id)


def select_for_pruning(backups: list[BackupInfo]) -> list[BackupInfo]:
    """Automatic backups beyond the newest 14, and Before upgrade beyond the newest 10."""
    pruned: list[BackupInfo] = []
    for kind, keep in (
        (BackupKind.AUTOMATIC, KEEP_AUTOMATIC),
        (BackupKind.BEFORE_UPGRADE, KEEP_BEFORE_UPGRADE),
    ):
        of_kind = [b for b in backups if not b.damaged and b.kind is kind]
        of_kind.sort(key=lambda b: b.created_at, reverse=True)
        pruned.extend(of_kind[keep:])
    return pruned


def most_recent(backups: list[BackupInfo]) -> BackupInfo | None:
    """The newest backup of any kind, across both locations (it can't be deleted)."""
    usable = [b for b in backups if not b.damaged]
    return max(usable, key=lambda b: b.created_at, default=None)


# --- Preferences and dashboard status --------------------------------------------------------


@dataclass
class BackupPrefs:
    version: int = 1
    auto_enabled: bool = True
    folder: str | None = None
    last_success_at: datetime | None = None
    last_auto_date: str | None = None  # local YYYY-MM-DD
    last_auto_ok: bool | None = None
    last_auto_error: str | None = None
    last_fallback_at: datetime | None = None


@dataclass(frozen=True)
class BackupWarning:
    message: str
    level: str = "warning"


def backup_status(prefs: BackupPrefs, key_set: bool, now: datetime) -> list[BackupWarning]:
    warnings: list[BackupWarning] = []
    if not key_set:
        warnings.append(BackupWarning("Set a backup password to start backing up."))
    if prefs.last_auto_ok is False:
        reason = prefs.last_auto_error or "unknown error."
        warnings.append(BackupWarning(f"The last automatic backup failed: {reason}", "error"))
    if prefs.last_fallback_at is not None:
        warnings.append(
            BackupWarning(
                "Your backup folder couldn't be reached, so backups were saved on this computer."
            )
        )
    if not prefs.auto_enabled:
        warnings.append(BackupWarning("Automatic backups are off."))
    if prefs.last_success_at is None:
        warnings.append(BackupWarning("No backups yet."))
    elif now - prefs.last_success_at > STALE_AFTER:
        warnings.append(BackupWarning("No backup in the last 7 days."))
    return warnings


# --- Passwords -------------------------------------------------------------------------------


def validate_new_password(password: str, confirm: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    text = unicodedata.normalize("NFC", password)
    if len(text) < MIN_PASSWORD or not text.strip():
        errors["password"] = "Use at least 10 characters."
    elif len(text) > MAX_PASSWORD:
        errors["password"] = "Use at most 1,024 characters."
    if password != confirm:
        errors["password_confirm"] = "The two passwords don't match."
    return errors
