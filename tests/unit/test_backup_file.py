"""The .fpbackup file format (contracts/backup-file.md)."""

from __future__ import annotations

import hashlib
import hmac
import json
import struct
import unicodedata

import pytest

from floorpro import backup_file as bf

DB_BYTES = b"SQLite format 3\x00" + bytes(range(256)) * 40
FIELDS = {
    "kind": "manual",
    "created_at": "2026-11-08T17:30:12.345678Z",
    "app_version": "0.2.0",
    "schema_revision": "0001",
    "contents": {"customers": 2},
}


@pytest.fixture
def kdf():
    return bf.new_kdf()


@pytest.fixture
def key(kdf):
    return bf.derive_key("correct horse battery", kdf)


@pytest.fixture
def written(tmp_path, key, kdf):
    return bf.write_backup(tmp_path, "b.fpbackup", DB_BYTES, FIELDS, key, kdf)


def _split(path):
    data = path.read_bytes()
    (length,) = struct.unpack(">I", data[16:20])
    return data, length


def _rewrite_header(path, change):
    data, length = _split(path)
    header = json.loads(data[20 : 20 + length])
    change(header)
    raw = json.dumps(header).encode()
    path.write_bytes(data[:16] + struct.pack(">I", len(raw)) + raw + data[20 + length :])


def test_round_trip(written, key):
    header = bf.read_header(written)
    assert header["kind"] == "manual"
    assert header["contents"] == {"customers": 2}
    assert bf.decrypt(written, key) == DB_BYTES


def test_layout(written):
    data, length = _split(written)
    assert data[:16] == b"FLOORPRO-BACKUP\x00"
    header = json.loads(data[20 : 20 + length].decode("utf-8"))
    for name in (
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
    ):
        assert name in header
    assert header["format_version"] == 1
    assert header["cipher"] == "AES-256-GCM"
    assert header["compression"] == "zlib"
    assert header["kdf"]["name"] == "scrypt"


def test_no_partial_left_behind(written):
    assert [p.name for p in written.parent.iterdir()] == ["b.fpbackup"]


def test_changed_header_byte_is_damaged(written, key):
    data, length = _split(written)
    header = data[20 : 20 + length].replace(b'"customers": 2', b'"customers": 3')
    assert header != data[20 : 20 + length]
    written.write_bytes(data[:20] + header + data[20 + length :])
    bf.read_header(written)  # still a readable header
    with pytest.raises(bf.BackupDamaged):
        bf.decrypt(written, key)


def test_flipped_payload_byte_is_damaged(written, key):
    data = bytearray(written.read_bytes())
    data[-30] ^= 0x01
    written.write_bytes(bytes(data))
    with pytest.raises(bf.BackupDamaged):
        bf.decrypt(written, key)


def test_truncated_file_is_damaged(written, key):
    data = written.read_bytes()
    written.write_bytes(data[:-100])
    with pytest.raises(bf.BackupDamaged):
        bf.decrypt(written, key)


@pytest.mark.parametrize(
    "content",
    [b"", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + b"x" * 500, bytes(range(256)) * 4],
)
def test_not_a_backup(tmp_path, content):
    path = tmp_path / "x.fpbackup"
    path.write_bytes(content)
    with pytest.raises(bf.NotABackup):
        bf.read_header(path)


def test_header_missing_key_is_not_a_backup(written):
    _rewrite_header(written, lambda h: h.pop("nonce"))
    with pytest.raises(bf.NotABackup):
        bf.read_header(written)


def test_newer_format_is_refused(written):
    _rewrite_header(written, lambda h: h.update(format_version=2))
    with pytest.raises(bf.BackupTooNew):
        bf.read_header(written)


def test_oversized_header_is_rejected(tmp_path):
    path = tmp_path / "big.fpbackup"
    path.write_bytes(bf.MAGIC + struct.pack(">I", 65537) + b"{" * 70000)
    with pytest.raises(bf.NotABackup):
        bf.read_header(path)


def test_wrong_password_is_distinct_from_damage(written):
    kdf = bf.KdfParams.from_header(bf.read_header(written)["kdf"])
    wrong = bf.derive_key("wrong password!", kdf)
    with pytest.raises(bf.WrongPassword) as excinfo:
        bf.decrypt(written, wrong)
    assert not isinstance(excinfo.value, bf.BackupDamaged)
    assert excinfo.value.message == "That password doesn't open this backup."


def test_key_from_header_kdf_opens_the_file(written):
    kdf = bf.KdfParams.from_header(bf.read_header(written)["kdf"])
    assert bf.decrypt(written, bf.derive_key("correct horse battery", kdf)) == DB_BYTES


def test_key_id(key):
    expected = hmac.new(key, b"floorpro-backup-key-id", hashlib.sha256).digest()[:16]
    assert bf.key_id(key) == expected


def test_password_is_nfc_normalised(kdf):
    text = "café au lait!"
    nfd = unicodedata.normalize("NFD", text)
    assert nfd != text
    assert bf.derive_key(nfd, kdf) == bf.derive_key(text, kdf)


def test_salt_changes_the_key():
    a, b = bf.new_kdf(), bf.new_kdf()
    assert a.salt != b.salt and len(a.salt) == 16
    assert bf.derive_key("same password", a) != bf.derive_key("same password", b)


def test_nonces_are_unique(tmp_path, key, kdf):
    one = bf.write_backup(tmp_path, "1.fpbackup", DB_BYTES, FIELDS, key, kdf)
    two = bf.write_backup(tmp_path, "2.fpbackup", DB_BYTES, FIELDS, key, kdf)
    assert bf.read_header(one)["nonce"] != bf.read_header(two)["nonce"]


def test_failed_write_leaves_nothing(tmp_path, key, kdf, monkeypatch):
    def boom(*_args):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(bf.os, "fsync", boom)
    with pytest.raises(OSError):
        bf.write_backup(tmp_path, "b.fpbackup", DB_BYTES, FIELDS, key, kdf)
    assert list(tmp_path.iterdir()) == []


def test_atomic_copy(written, tmp_path):
    dest = tmp_path / "copies" / "copy.fpbackup"
    dest.parent.mkdir()
    bf.atomic_copy(written, dest)
    assert dest.read_bytes() == written.read_bytes()
    assert [p.name for p in dest.parent.iterdir()] == ["copy.fpbackup"]


def test_production_kdf_default(monkeypatch):
    monkeypatch.undo()  # remove the fast_kdf patch
    assert (bf.DEFAULT_KDF.n, bf.DEFAULT_KDF.r, bf.DEFAULT_KDF.p) == (131072, 8, 1)
    assert bf.new_kdf().n == 131072
