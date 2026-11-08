# Data Model: Currency & VAT Settings and Customer Records

**Feature**: 001-settings-customer-records | **Date**: 2026-11-08

Storage: SQLite, through SQLAlchemy 2.x models and Alembic migration `0001_initial`.
Conventions:
- **Money** is stored as integer minor units and **percentages** as integer basis points. Both
  are exposed to code as `Decimal` (see [research.md §2](research.md#2-storing-money-and-percentages)).
- **Timestamps** are UTC.
- **Booleans** are stored as `INTEGER 0/1`.

---

## 1. `business_settings` (single row)

The business-wide currency and VAT configuration (spec: Business Settings, FR-001–FR-010).

| Field | Type (DB) | Code type | Default | Rules |
|-------|-----------|-----------|---------|-------|
| `id` | INTEGER PK | int | 1 | `CHECK (id = 1)`, so there's only ever one row |
| `currency_code` | TEXT(3) NOT NULL | `str` | `'GBP'` | Must be in the supported currency list (FR-003) |
| `vat_registered` | INTEGER NOT NULL | `bool` | `1` | |
| `vat_rate_bp` | INTEGER NOT NULL | `Decimal` percent | `2000` (20%) | `CHECK (vat_rate_bp BETWEEN 0 AND 10000)`, at most 2 dp (FR-004) |
| `vat_number` | TEXT NULL | `str \| None` | NULL | Stored normalised (no spaces, upper case). Must match the UK format when present (FR-005). Only required to be valid when `vat_registered` is true |
| `price_entry_mode` | TEXT NOT NULL | `PriceEntryMode` enum | `'inc_vat'` | `CHECK (price_entry_mode IN ('inc_vat','ex_vat'))` (FR-010) |
| `updated_at` | DATETIME NOT NULL | `datetime` (UTC) | now | Set on every save |

**Supported currencies** (a code constant in `floorpro/domain/currency.py`, not a table): the
list is easy to extend.

| Code | Symbol | Name |
|------|--------|------|
| GBP | £ | Pound sterling |
| EUR | € | Euro |
| USD | $ | US dollar |

**Behaviour**
- On startup, if the row is missing, it's created with the defaults and a one-time notice is
  shown (spec edge case).
- When `vat_registered` is false, `vat_rate_bp` and `vat_number` are kept (so switching back
  restores them) but treated as not applicable.
- Saving a change to any field except `updated_at` writes one `settings_change` row per
  changed field, in the same transaction.

## 2. `settings_change` (append-only history)

FR-007, FR-010: which settings were in force at any date.

| Field | Type (DB) | Rules |
|-------|-----------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `change_set_id` | TEXT(36) NOT NULL | UUID shared by all rows written in one save |
| `changed_at` | DATETIME NOT NULL | UTC. Indexed |
| `field` | TEXT NOT NULL | `CHECK (field IN ('currency_code','vat_registered','vat_rate','vat_number','price_entry_mode'))` |
| `old_value` | TEXT NULL | Canonical string form (e.g. `'20.00'`, `'true'`, `'GBP'`) |
| `new_value` | TEXT NULL | Same format |

**Rules**: Rows are never updated or deleted by the application. "Settings in force at time
T" = start from the defaults and apply all changes with `changed_at <= T` in order. A service
function implements this, and unit tests cover it.

## 3. `customer`

A person or business the shop deals with (spec: Customer, FR-011–FR-029).

| Field | Type (DB) | Rules |
|-------|-----------|-------|
| `id` | INTEGER PK AUTOINCREMENT | Never reused (FR-013) |
| `customer_type` | TEXT NOT NULL | `CHECK (customer_type IN ('domestic','trade'))`. Default `'domestic'` (FR-025) |
| `show_vat_breakdown` | INTEGER NOT NULL | Default `0`. `CHECK (customer_type = 'domestic' OR show_vat_breakdown = 1)` (FR-026) |
| `title` | TEXT NULL | Free text up to 20 chars (Mr, Mrs, Ms, Dr, …) |
| `first_name` | TEXT NULL | Up to 100 chars, trimmed |
| `last_name` | TEXT NULL | Up to 100 chars, trimmed. Indexed, `NOCASE` |
| `company_name` | TEXT NULL | Up to 200 chars, trimmed. Indexed, `NOCASE` |
| `mobile_phone` | TEXT NULL | As entered (trimmed), up to 30 chars |
| `mobile_phone_digits` | TEXT NULL | Derived: digits only, with `+44` → `0`. Indexed |
| `other_phone` | TEXT NULL | As entered, up to 30 chars |
| `other_phone_digits` | TEXT NULL | Derived as above. Indexed |
| `email` | TEXT NULL | Valid format (FR-014), stored trimmed. Indexed, `NOCASE` |
| `address_line1` | TEXT NULL | Up to 200 chars |
| `address_line2` | TEXT NULL | Up to 200 chars |
| `town` | TEXT NULL | Up to 100 chars |
| `county` | TEXT NULL | Up to 100 chars |
| `postcode` | TEXT NULL | Normalised `SW1A 1AA` format when recognisable, otherwise stored as entered (upper case) with a warning |
| `postcode_compact` | TEXT NULL | Derived: upper case, no spaces. Indexed |
| `notes` | TEXT NULL | No length limit (spec edge case) |
| `marketing_consent` | INTEGER NOT NULL | Default `0` |
| `is_archived` | INTEGER NOT NULL | Default `0`. Indexed |
| `archived_at` | DATETIME NULL | Set when archived, cleared when restored |
| `created_at` | DATETIME NOT NULL | UTC (FR-018) |
| `updated_at` | DATETIME NOT NULL | UTC, set on every change (FR-018) |

**Table constraints (data integrity, also enforced in the service with friendly messages)**
- `CHECK (COALESCE(TRIM(first_name),'') <> '' OR COALESCE(TRIM(last_name),'') <> '' OR COALESCE(TRIM(company_name),'') <> '')`.
  Needs a person's name or a company name (FR-012).
- `CHECK (mobile_phone IS NOT NULL OR other_phone IS NOT NULL OR email IS NOT NULL)`. Needs at
  least one contact method (FR-012). Empty strings are stored as NULL.
- The VAT-breakdown check above enforces FR-026 even if the service has a bug.

**Derived values (not stored)**
- `reference`: `C-{id:05d}` (e.g. `C-00042`), computed from `id`, which `AUTOINCREMENT`
  never reuses (FR-013). Search recognises `C-00042`, `c42` and `C42` (regex
  `^c-?0*(\d+)$`, case-insensitive) and matches on `id`.
- `display_name`: company name if set, otherwise "First Last". When both are present the list
  shows "Company (First Last)".
- `sort_name`: `last_name, first_name` or the company name, used for "sort by name"
  (FR-017).

**Duplicate detection (FR-015)**: when creating (and when editing, if the phone or email
changed), find active or archived customers other than this one where any of these match:
- `mobile_phone_digits` / `other_phone_digits` equals either new phone (digits)
- `email` matches case-insensitively

### State transitions

```text
                 archive (confirm)
   ┌────────┐  ─────────────────▶  ┌──────────┐
   │ Active │                      │ Archived │
   └────────┘  ◀─────────────────  └──────────┘
       │             restore             │
       │ erase (type name to confirm)    │ erase
       ▼                                 ▼
   [Deleted]  ← no linked records (always true in this feature)
   [Anonymised] ← has linked records (built with the first feature that adds them)
```

Archived customers are left out of the default list and search (FR-017) but still count for
duplicate detection.

### Customer type rules (FR-025–FR-027)

| Change | Effect on `show_vat_breakdown` |
|--------|--------------------------------|
| New customer, type domestic | Defaults to `false`, editable |
| New customer, type trade | Forced `true`, locked |
| domestic → trade | Forced `true`, locked |
| trade → domestic | Stays `true`, becomes editable |
| domestic, user toggles | Saved as chosen |

These rules are a pure function, `resolve_vat_breakdown(old_type, new_type,
requested_value)`, in `floorpro/domain/customers.py`, written test-first.

---

## Relationships

None in this feature. Future features add `job.customer_id`, `appointment.customer_id`,
`order.customer_id` and `invoice.customer_id` → `customer.id` (`ON DELETE RESTRICT`). These
links will drive `has_linked_records()` and the anonymise path.

## Indexes summary

`customer`: `last_name`, `company_name`, `email`,
`mobile_phone_digits`, `other_phone_digits`, `postcode_compact`,
`(is_archived, customer_type)`.
`settings_change`: `changed_at`.
