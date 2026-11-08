# Quickstart & Validation: Currency & VAT Settings and Customer Records

**Feature**: 001-settings-customer-records | **Date**: 2026-11-08

This guide shows how to run FloorPro and prove that this feature works end to end. Details
live in [data-model.md](data-model.md), [contracts/routes.md](contracts/routes.md) and
[contracts/customer-export.md](contracts/customer-export.md).

## Prerequisites

- macOS or Windows 10/11 (Windows needs the WebView2 runtime, which Windows 10/11 already
  includes)
- [uv](https://docs.astral.sh/uv/) 0.13+ (uv installs Python 3.13 itself, so no system
  Python is needed)
- Git and a clone of `RSmithCoding/Floor-Pro`

## Setup (one time)

```bash
uv sync                          # creates .venv with Python 3.13 and all locked dependencies
uv run python scripts/fetch_tailwind.py   # downloads the pinned Tailwind standalone CLI
uv run python scripts/build_css.py        # compiles static/css/app.css
```

## Run

```bash
uv run python -m floorpro              # native desktop window (pywebview)
uv run python -m floorpro --browser    # same app in your normal browser (development)
uv run python scripts/build_css.py --watch   # optional, in a second terminal while editing templates
```

**Data location** (created on first run):
- macOS: `~/Library/Application Support/FloorPro/floorpro.db`
- Windows: `%LOCALAPPDATA%\FloorPro\floorpro.db`

To start from a clean state, quit the app and move that folder aside.

## Automated checks (same as CI)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest                    # unit + integration + migration tests
uv run pytest -m slow            # only the 10,000-customer search performance test
```

**Expected**: everything passes. CI runs the same commands on macOS and Windows for every push
(`.github/workflows/ci.yml`).

## Manual validation scenarios

Run these in the desktop window. Each maps to the spec's acceptance scenarios.

### A. Settings defaults and changes (User Story 2)

1. **First run defaults**: on a fresh data folder, open **Settings**. Expect GBP (£), VAT
   registered ticked, VAT rate 20, price entry mode "Prices include VAT".
2. **Change the VAT rate**: set the rate to `17.5` and save. Expect a confirmation dialog
   showing "VAT rate: 20% → 17.5%" and "applies to new quotes and invoices only".
   Confirm. Expect a "Settings saved" toast and a new row in the history.
3. **Invalid rates**: try `-5`, `150` and `abc`. Each is blocked with "Enter a VAT rate
   between 0 and 100, with up to two decimal places."
4. **Not VAT registered**: untick VAT registered. Expect the VAT rate and number to be
   optional, then save successfully.
5. **Currency**: change to EUR and confirm. Expect currency amounts to show `€`.
6. **Price entry mode**: switch to "Prices exclude VAT" and confirm. Expect it in the
   history.
7. **Persistence**: quit and relaunch. Expect all the changes above to still be there.

### B. Add and find customers (User Story 1)

1. **Add a customer**: Customers → **Add customer** → enter `Jane Smith`, mobile
   `07700 900123`, postcode `bs1 4dj` → save. Expect to be taken to the record showing
   reference `C-00001`, postcode `BS1 4DJ` and type Domestic.
2. **Missing name**: save with no name and no company. Expect the error next to the name
   fields.
3. **No contact method**: save with no phone or email. Expect "Add a phone number or email
   address."
4. **Search by phone**: in the list, type `07700900123`. Expect Jane Smith to appear while
   you type.
5. **Search by postcode**: type `BS1`. Expect the match.
6. **Duplicate warning**: add a new customer with mobile `07700 900123`. Expect a warning
   linking to C-00001 and a **Save anyway** option.
7. **No results**: search `zzz`. Expect the empty state with "Add 'zzz' as a new customer".
8. **Unsaved changes**: start adding a customer, type a name, then click **Settings** in the
   nav. Expect a "You have unsaved changes. Discard them?" dialog. **Keep editing** stays on
   the form. **Discard** leaves the form.
9. **Persistence**: quit and relaunch. Expect every customer you added to still be there with
   all details.

### C. Domestic and trade (User Story 4)

1. **Trade customer**: new customer, choose **Trade**. Expect "Show VAT breakdown" to become
   ticked and locked, with a hint, and the company name field to be prominent.
2. **Domestic with breakdown**: open Jane Smith (domestic), tick "Show VAT breakdown" and
   save. Expect it to be saved.
3. **Trade → domestic**: change a trade customer to domestic. Expect the breakdown to stay
   ticked but become editable.
4. **Filter**: in the list, filter **Trade**. Expect only trade customers, each showing a type
   badge.

### D. Manage customer data (User Story 3)

1. **Edit**: change Jane's phone number and save. Expect the new number and an updated
   "Last updated" time.
2. **Archive**: archive Jane and confirm. Expect her to be gone from the default list and
   visible with **Show archived**. Restore her.
3. **Export**: click Export. A native save dialog appears. Save the file and open it. Expect
   JSON matching [customer-export.md](contracts/customer-export.md).
4. **Erase**: choose Erase, type the wrong name (expect an error), then type `Jane Smith`.
   Expect the customer to be gone. A new customer then gets the next reference, never a
   reused one.

### E. Migration safety (Constitution, Principle I)

1. With an existing data folder, run a build that adds a newer migration. Expect a file
   `backups/floorpro-<timestamp>-pre-<rev>.db` to be created before the upgrade, with all
   data intact afterwards. (This is covered automatically by `tests/migrations/`.)

## Done when

- All automated checks pass locally and on both CI platforms.
- Scenarios A–D behave as described in the desktop window on macOS.
- Each page and HTMX update feels instant (under 300 ms), including search with 10,000
  customers (the `slow` test).
