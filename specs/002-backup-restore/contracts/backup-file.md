# Backup File Format: `.fpbackup` (format version 1)

**Feature**: 002-backup-restore

This file format is a long-lived contract. Every future FloorPro version MUST be able to
restore format version 1 files. Rationale is in [research §2–§3](../research.md#2-file-format).

## Layout

All integers are big-endian. The layout is the same on every platform.

| Offset | Length | Content |
|--------|--------|---------|
| 0 | 16 | Magic: ASCII `FLOORPRO-BACKUP` followed by one `0x00` byte |
| 16 | 4 | `H`: header length in bytes (unsigned, 1 ≤ H ≤ 65,536) |
| 20 | H | Header: UTF-8 JSON object (below) |
| 20 + H | rest | Payload: AES-256-GCM ciphertext followed by its 16-byte tag |

**Associated data** for AES-GCM: bytes `0 … 20 + H − 1` (magic, length and header). Changing
any header byte makes decryption fail.

**Plaintext** of the payload: the SQLite database file, compressed with zlib
(`zlib.compress(data, 6)`).

## Header

```json
{
  "format_version": 1,
  "kind": "manual",
  "created_at": "2026-11-08T17:30:12.345678Z",
  "app_version": "0.2.0",
  "schema_revision": "0001",
  "contents": {"customers": 1234},
  "cipher": "AES-256-GCM",
  "compression": "zlib",
  "kdf": {"name": "scrypt", "n": 131072, "r": 8, "p": 1, "salt": "base64…"},
  "key_id": "base64…",
  "nonce": "base64…"
}
```

| Key | Rules |
|-----|-------|
| `format_version` | integer; readers refuse values greater than they support ("newer version" message) |
| `kind` | `manual` \| `automatic` \| `before_restore` \| `before_upgrade` |
| `created_at` | UTC, ISO 8601 with `Z` |
| `app_version` | FloorPro package version, for display |
| `schema_revision` | Alembic revision string, or `null` for a database at `base`; unknown revisions are refused as "newer version" |
| `contents` | object of non-negative integers; `customers` always present; readers ignore unknown keys |
| `cipher`, `compression` | must be exactly these values in format version 1 |
| `kdf.salt` | 16 random bytes, standard base64 |
| `key_id` | 16 bytes: `HMAC-SHA256(key, b"floorpro-backup-key-id")[:16]` |
| `nonce` | 12 random bytes, unique per file |

The header MUST NOT contain any customer data (names, phones, emails, addresses) or file
paths. Readers ignore unknown header keys, so later versions can add fields without bumping
`format_version`.

## Deriving the key

```text
password_bytes = NFC(password).encode("utf-8")
key = scrypt(password_bytes, salt=kdf.salt, n=kdf.n, r=kdf.r, p=kdf.p, dklen=32)
```

`key_id` is checked first: a mismatch means the wrong password. If the key id matches but the
tag check fails, the file is damaged.

## Reader outcomes

| Condition | Result (message shown to the user) |
|-----------|------------------------------------|
| Magic missing, header unreadable or not JSON, required key missing | "This file isn't a FloorPro backup, or it's damaged." |
| `format_version` > supported, or unknown `schema_revision` | "This backup was made by a newer version of FloorPro. Update FloorPro first." |
| Key id doesn't match the key from the given password | "That password doesn't open this backup." |
| No password given and key id isn't this computer's | the password field is shown: "Enter the password this backup was made with." |
| Tag check fails, decompression fails, or `integrity_check` isn't `ok` | "This backup is damaged and can't be used. Your current data hasn't been changed." |
| Required tables missing after decryption | same as damaged |

## Legacy pre-upgrade copies

The pre-migration copies written by feature 001, `floorpro-<UTC stamp>-pre-<rev>.db`, are
plain SQLite files. They are listed as "Before upgrade · Not protected". From the Backups
screen they're listed only; in recovery mode they can be restored.
They are converted to `.fpbackup` (kind `before_upgrade`, `created_at` taken from the stamp in
the name) when a backup password is first set.

## Test fixture

`tests/fixtures/backup-v1.fpbackup` is a committed format-version-1 file made with the password
`correct horse battery` and small KDF parameters (`n=1024`). Every platform's test suite
restores it (SC-006). It must never be regenerated in a way that changes the format.
