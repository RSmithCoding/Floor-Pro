# Contract: Customer Data Export File

**Feature**: 001-settings-customer-records | **Requirement**: FR-020

The file produced by `GET /customers/{id}/export` for a data-protection request. It's
pretty-printed JSON (UTF-8, 2-space indent) with plain-English keys, so a non-technical person
can read it and other software can parse it.

**Filename**: `FloorPro-customer-{reference}-{YYYY-MM-DD}.json`

## Format (version 1)

```json
{
  "export": {
    "format_version": 1,
    "produced_by": "FloorPro",
    "exported_at": "2026-11-07T14:05:00Z",
    "description": "All personal data FloorPro holds about this customer."
  },
  "customer": {
    "reference": "C-00042",
    "customer_type": "domestic",
    "show_vat_breakdown": false,
    "title": "Mrs",
    "first_name": "Jane",
    "last_name": "Smith",
    "company_name": null,
    "mobile_phone": "07700 900123",
    "other_phone": null,
    "email": "jane.smith@example.com",
    "address": {
      "line_1": "1 High Street",
      "line_2": null,
      "town": "Bristol",
      "county": null,
      "postcode": "BS1 4DJ"
    },
    "notes": "Prefers morning appointments.",
    "marketing_consent": false,
    "archived": false,
    "archived_at": null,
    "created_at": "2026-11-07T10:00:00Z",
    "updated_at": "2026-11-07T10:00:00Z"
  },
  "related_records": {
    "jobs": [],
    "orders": [],
    "appointments": [],
    "invoices": []
  }
}
```

## Rules

- Every stored customer field appears in the file, including empty ones (`null`). The derived
  search columns (`*_digits`, `postcode_compact`) are left out, because they only repeat
  data already in the file.
- Timestamps are ISO 8601 UTC with a `Z` suffix.
- `related_records` keys are present now and empty. Later features fill them in, and
  `format_version` goes up only if an existing key changes meaning.
- Integration tests check that the file parses, that every column in the `customer` table
  except the derived ones and `id` is present, and the filename format.
