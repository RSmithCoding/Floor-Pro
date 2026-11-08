"""Reading and writing ``.fpbackup`` files (format version 1).

The format is a long-lived contract: see specs/002-backup-restore/contracts/backup-file.md.
This module imports only the standard library and ``cryptography``'s AES-GCM. It knows
nothing about the database or the web layer.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import shutil
import struct
import unicodedata
import zlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"FLOORPRO-BACKUP\x00"
FORMAT_VERSION = 1
MAX_HEADER = 65536
EXTENSION = ".fpbackup"
CIPHER = "AES-256-GCM"
COMPRESSION = "zlib"
KEY_ID_LABEL = b"floorpro-backup-key-id"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
_PREFIX = len(MAGIC) + 4
REQUIRED_KEYS = (
    "format_version",
    "kind",
    "created_at",
    "app_version",
    "schema_revision",
    "contents",
    "cipher",
    "compression",
    "kdf",
    "key_id",
    "nonce",
)


# --- Errors (each carries the message shown to the user) -------------------------------------


class BackupError(Exception):
    message = "The backup couldn't be used."

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class NotABackup(BackupError):
    message = "This file isn't a FloorPro backup, or it's damaged."


class BackupDamaged(BackupError):
    message = "This backup is damaged and can't be used. Your current data hasn't been changed."


class BackupTooNew(BackupError):
    message = "This backup was made by a newer version of FloorPro. Update FloorPro first."


class WrongPassword(BackupError):
    message = "That password doesn't open this backup."


# --- Keys ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class KdfParams:
    n: int
    r: int
    p: int
    salt: bytes = b""

    def to_header(self) -> dict[str, Any]:
        return {"name": "scrypt", "n": self.n, "r": self.r, "p": self.p, "salt": _b64(self.salt)}

    @classmethod
    def from_header(cls, data: Any) -> KdfParams:
        try:
            if data["name"] != "scrypt":
                raise NotABackup()
            params = cls(int(data["n"]), int(data["r"]), int(data["p"]), _unb64(data["salt"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise NotABackup() from exc
        if params.n < 2 or params.n & (params.n - 1) or params.r < 1 or params.p < 1:
            raise NotABackup()
        return params


DEFAULT_KDF = KdfParams(n=131072, r=8, p=1)


def new_kdf() -> KdfParams:
    """The current default parameters with a fresh random salt."""
    return replace(DEFAULT_KDF, salt=secrets.token_bytes(SALT_BYTES))


def derive_key(password: str, kdf: KdfParams) -> bytes:
    data = unicodedata.normalize("NFC", password).encode("utf-8")
    maxmem = max(256 * 1024 * 1024, 129 * kdf.n * kdf.r * kdf.p + 1024 * 1024)
    return hashlib.scrypt(
        data, salt=kdf.salt, n=kdf.n, r=kdf.r, p=kdf.p, maxmem=maxmem, dklen=KEY_BYTES
    )


def key_id(key: bytes) -> bytes:
    return hmac.new(key, KEY_ID_LABEL, hashlib.sha256).digest()[:16]


# --- Reading ---------------------------------------------------------------------------------


def _read_prefix(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Return (associated data, header) after validating the header."""
    try:
        with open(path, "rb") as fh:
            start = fh.read(_PREFIX)
            if len(start) < _PREFIX or start[: len(MAGIC)] != MAGIC:
                raise NotABackup()
            (length,) = struct.unpack(">I", start[len(MAGIC) :])
            if not 1 <= length <= MAX_HEADER:
                raise NotABackup()
            raw = fh.read(length)
    except OSError as exc:
        raise NotABackup() from exc
    if len(raw) < length:
        raise NotABackup()
    try:
        header = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise NotABackup() from exc
    if not isinstance(header, dict):
        raise NotABackup()
    version = header.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise NotABackup()
    if version > FORMAT_VERSION:
        raise BackupTooNew()
    if any(name not in header for name in REQUIRED_KEYS):
        raise NotABackup()
    if header["cipher"] != CIPHER or header["compression"] != COMPRESSION:
        raise NotABackup()
    contents = header["contents"]
    if not isinstance(contents, dict) or not isinstance(contents.get("customers"), int):
        raise NotABackup()
    KdfParams.from_header(header["kdf"])
    try:
        if len(_unb64(header["key_id"])) != 16 or len(_unb64(header["nonce"])) != NONCE_BYTES:
            raise NotABackup()
    except (TypeError, ValueError) as exc:
        raise NotABackup() from exc
    return start + raw, header


def read_header(path: Path) -> dict[str, Any]:
    """Read and validate only the plaintext header (no password needed)."""
    return _read_prefix(path)[1]


def header_key_id(header: dict[str, Any]) -> bytes:
    return _unb64(header["key_id"])


def decrypt(path: Path, key: bytes) -> bytes:
    """Return the database bytes. Raises WrongPassword or BackupDamaged."""
    aad, header = _read_prefix(path)
    if not hmac.compare_digest(key_id(key), header_key_id(header)):
        raise WrongPassword()
    try:
        with open(path, "rb") as fh:
            fh.seek(len(aad))
            ciphertext = fh.read()
    except OSError as exc:
        raise BackupDamaged() from exc
    try:
        compressed = AESGCM(key).decrypt(_unb64(header["nonce"]), ciphertext, aad)
        return zlib.decompress(compressed)
    except (InvalidTag, zlib.error, ValueError) as exc:
        raise BackupDamaged() from exc


# --- Writing ---------------------------------------------------------------------------------


def build_header(fields: dict[str, Any], key: bytes, kdf: KdfParams, nonce: bytes) -> bytes:
    header = {
        "format_version": FORMAT_VERSION,
        "kind": fields["kind"],
        "created_at": fields["created_at"],
        "app_version": fields["app_version"],
        "schema_revision": fields["schema_revision"],
        "contents": fields["contents"],
        "cipher": CIPHER,
        "compression": COMPRESSION,
        "kdf": kdf.to_header(),
        "key_id": _b64(key_id(key)),
        "nonce": _b64(nonce),
    }
    raw = json.dumps(header, separators=(",", ": ")).encode("utf-8")
    if len(raw) > MAX_HEADER:
        raise ValueError("backup header too large")
    return raw


def write_backup(
    target_dir: Path,
    filename: str,
    db_bytes: bytes,
    fields: dict[str, Any],
    key: bytes,
    kdf: KdfParams,
) -> Path:
    """Compress, encrypt and atomically write a backup file. Returns its path."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    raw = build_header(fields, key, kdf, nonce)
    aad = MAGIC + struct.pack(">I", len(raw)) + raw
    ciphertext = AESGCM(key).encrypt(nonce, zlib.compress(db_bytes, 6), aad)
    target = Path(target_dir) / filename
    _atomic_write(target, lambda fh: (fh.write(aad), fh.write(ciphertext)))
    return target


def atomic_copy(src: Path, dest: Path) -> Path:
    """Copy a file so that ``dest`` only ever appears complete."""
    with open(src, "rb") as source:
        _atomic_write(Path(dest), lambda fh: shutil.copyfileobj(source, fh, 1024 * 1024))
    return Path(dest)


def atomic_write_bytes(target: Path, data: bytes) -> Path:
    """Write ``data`` so that ``target`` is replaced in one step (used for the JSON stores)."""
    _atomic_write(Path(target), lambda fh: fh.write(data))
    return Path(target)


def partial_name() -> str:
    return f".FloorPro-{secrets.token_hex(8)}.partial"


def _atomic_write(target: Path, write) -> None:
    partial = target.parent / partial_name()
    try:
        with open(partial, "xb") as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(partial, target)
    except BaseException:
        with contextlib.suppress(OSError):
            partial.unlink()
        raise


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: Any) -> bytes:
    if not isinstance(text, str):
        raise ValueError("expected base64 text")
    return base64.b64decode(text.encode("ascii"), validate=True)
