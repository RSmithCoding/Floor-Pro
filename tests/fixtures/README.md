# Test fixtures

Files here are long-lived contract fixtures. They MUST NOT be regenerated in a way that
changes their format: newer FloorPro versions must keep reading them.

## `backup-v1.fpbackup`

A format-version-1 backup (see `specs/002-backup-restore/contracts/backup-file.md`), made by
`scripts/make_backup_fixture.py` with the password `correct horse battery` and small scrypt
parameters (`n=1024, r=8, p=1`). It is restored by the test suite on macOS and Windows (SC-006).

Contents (schema revision `0001`, header `contents.customers == 3`):

| id | Type | Name | Archived |
|----|------|------|----------|
| 1 | domestic | Ada Lovelace (mobile 07700 900001, postcode SW1A 1AA) | no |
| 2 | trade | Brunel Flooring Ltd (other phone 0117 496 0002) | no |
| 3 | domestic | Charles Babbage (mobile 07700 900003) | yes |

Business settings: GBP, VAT registered, VAT rate 17.5% (`vat_rate_bp = 1750`), prices
entered inc VAT. Settings history: one change, `vat_rate` from `20.00` to `17.50`.
