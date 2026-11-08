# Feature Specification: Currency & VAT Settings and Customer Records

**Feature Branch**: `main` (no feature branch created)

**Created**: 2026-11-07

**Status**: Draft

**Input**: User description: "settings for currency and VAT, plus customer records"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add and find customers (Priority: P1)

A member of shop staff is serving someone at the counter or on the phone. They add the person
as a new customer (name, contact details, address, notes) in a few seconds. Later, they find
that customer again by typing part of a name, phone number, postcode or email.

**Why this priority**: Every later feature (estimates, planner, jobs, orders, invoices) is
attached to a customer. Without customer records, nothing else in FloorPro can be used.

**Independent Test**: Start with an empty app, add several customers, close and reopen the
app, and confirm each one can be found by name, phone, postcode and email with all details
intact.

**Acceptance Scenarios**:

1. **Given** the customer list is open, **When** staff enter a name, a phone number and an
   address and save, **Then** the customer is stored, given a unique customer reference, and
   their record is shown.
2. **Given** staff try to save a customer with no name, **When** they save, **Then** the save is
   blocked and the missing field is highlighted with a plain-English message.
3. **Given** staff try to save a customer with neither a phone number nor an email address,
   **When** they save, **Then** the save is blocked and they're told at least one contact
   method is needed.
4. **Given** 5,000 customers exist, **When** staff type "SW1A" in the search box, **Then**
   matching customers (by postcode) appear as they type.
5. **Given** a customer exists with phone number 07700 900123, **When** staff search
   "07700900123" (without the space), **Then** that customer is found.
6. **Given** staff are adding a customer whose phone number or email matches an existing
   customer, **When** they save, **Then** they're warned about the possible duplicate, shown
   the existing record, and can open it or carry on saving.

---

### User Story 2 - Set currency and VAT (Priority: P2)

The shop owner opens Settings and checks or changes the currency and VAT details the business
uses: the currency, whether the business is VAT registered, the VAT rate, and the VAT
registration number. On first launch these are already set to GBP and 20% VAT.

**Why this priority**: Quotes and invoices (future features) depend on these values. Setting
them correctly up front keeps every later figure right. Defaults mean most UK shops can skip
this step at first, so it ranks below customer records.

**Independent Test**: Launch a fresh install, open Settings, confirm the GBP / 20% defaults,
change them, restart the app, and confirm the new values are kept and shown across the app.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the user opens Settings, **Then** the currency is GBP
   (£), the business is marked VAT registered, and the VAT rate is 20%.
2. **Given** the Settings screen, **When** the user changes the VAT rate to 17.5% and saves,
   **Then** they're asked to confirm, told that the change applies only to new quotes and
   invoices, and after confirming the new rate is saved.
3. **Given** the Settings screen, **When** the user enters a VAT rate of -5, 150 or "abc",
   **Then** the save is blocked with a message stating the allowed range (0–100%, up to two
   decimal places).
4. **Given** the business is marked as not VAT registered, **When** the user saves, **Then** the
   VAT rate and VAT number fields are not required and VAT will not be applied to new
   documents.
5. **Given** the user changes the currency to EUR, **When** they view any money amount in the
   app, **Then** it's shown with the € symbol and two decimal places. No existing amounts are
   converted.
6. **Given** a fresh install, **When** the user opens Settings, **Then** the price entry mode is
   "prices include VAT".
7. **Given** the Settings screen, **When** the user switches the price entry mode to "prices
   exclude VAT" and confirms, **Then** prices typed in from then on are treated as before VAT,
   and any price already stored keeps exactly the value it had.

---

### User Story 3 - Update, archive and manage customer data (Priority: P3)

Staff update a customer's details when they change (new phone number, moved house). They
archive customers who are no longer active so the main list stays tidy. When a customer makes
a data-protection request, the shop can export everything held about that person, or erase
their personal details.

**Why this priority**: Keeping records accurate and meeting data-protection obligations
matters, but a shop can start trading with Stories 1 and 2 alone.

**Independent Test**: Edit a customer and confirm changes persist. Archive one and confirm it
drops out of the default list but can still be found with "show archived". Export one and
confirm the file contains all their details. Erase one and confirm their personal details are
gone.

**Acceptance Scenarios**:

1. **Given** an existing customer, **When** staff change their phone number and save, **Then**
   the new number is shown everywhere that customer appears, and the record shows when it was
   last updated.
2. **Given** an active customer, **When** staff archive them and confirm, **Then** they no
   longer appear in the default customer list or search, but appear when "show archived" is
   on, and can be restored.
3. **Given** a customer, **When** staff choose "export customer data", **Then** a readable file
   is produced containing every detail FloorPro holds about that customer.
4. **Given** a customer with no linked jobs, orders or invoices, **When** staff choose "erase"
   and confirm by typing the customer's name, **Then** the customer is permanently deleted.
5. **Given** a customer who has linked financial records (once those features exist), **When**
   staff choose "erase" and confirm, **Then** the customer's personal details are anonymised,
   while the financial records are kept as the law requires.

---

### User Story 4 - Domestic and trade customers (Priority: P3)

Staff mark each customer as **domestic** (a member of the public) or **trade** (fitters,
builders, landlords, other businesses). The type controls how VAT will be shown on that
customer's quotes and invoices. Domestic customers normally get a single total that includes
VAT. Trade customers always get a full VAT breakdown. A domestic customer who needs a
breakdown (for example for an insurance claim) can have it switched on for their record.

**Why this priority**: Shops serve both groups and present prices to them differently.
Capturing the type now means later quoting and invoicing work correctly from day one, without
having to classify existing customers afterwards.

**Independent Test**: Create one domestic and one trade customer. Confirm each shows its type
and VAT display preference, that the list can be filtered by type, and that the trade
customer's VAT breakdown preference can't be turned off.

**Acceptance Scenarios**:

1. **Given** staff are adding a new customer, **When** they don't choose a type, **Then** the
   customer is saved as domestic, with "show VAT breakdown" off.
2. **Given** staff are adding a customer, **When** they choose "trade", **Then** "show VAT
   breakdown" is switched on and locked on, and a company/trading name field is offered.
3. **Given** a domestic customer needs a VAT breakdown for an insurance job, **When** staff turn
   on "show VAT breakdown" on that customer's record, **Then** the preference is saved and
   shown on the record.
4. **Given** a domestic customer with "show VAT breakdown" on, **When** staff change them to
   trade, **Then** the preference stays on and becomes locked. **When** a trade customer is
   changed to domestic, **Then** the preference stays on until staff turn it off.
5. **Given** customers of both types exist, **When** staff filter the customer list by "trade",
   **Then** only trade customers are shown, and each row in the list shows the customer's
   type.

---

### Edge Cases

- Customer has only a company name and no individual's name: accepted if company name is given
  (the "name" requirement is met by either a person's name or a company name).
- Postcode entered in lower case or without a space ("sw1a1aa"): stored and shown in standard
  format ("SW1A 1AA"). Clearly invalid UK postcodes produce a warning but don't block saving,
  so unusual addresses can still be recorded.
- Two customers with identical names (e.g. two "John Smith"s): allowed. They're told apart by
  customer reference, address and phone number.
- Very long notes (several thousand characters): stored in full and shown without breaking the
  layout.
- Search with no matches: a clear "no customers found" message with a shortcut to add a new
  customer, pre-filled with what was typed.
- User leaves a customer form with unsaved changes: asked whether to discard them.
- VAT rate changed to 0%: allowed (differs from "not VAT registered" in that the VAT line still
  appears on documents at 0%).
- Settings data missing on startup: the app restores the defaults (GBP, 20%) and tells the
  user it did so. (Recovering from a corrupted database file belongs to the future backup and
  restore feature.)

## Requirements *(mandatory)*

### Functional Requirements

**Settings – currency and VAT**

- **FR-001**: System MUST provide a Settings screen where the user can view and change the
  currency, VAT registration status, VAT rate, and VAT registration number.
- **FR-002**: On first launch, the system MUST default to currency GBP (£), VAT registered,
  and a VAT rate of 20%.
- **FR-003**: System MUST let the user choose the currency from a predefined list of common
  currencies, each with its symbol (at minimum GBP £, EUR €, USD $).
- **FR-004**: System MUST accept VAT rates from 0% to 100% inclusive, with up to two decimal
  places, and reject anything else with a clear message.
- **FR-005**: System MUST accept a VAT registration number when the business is VAT
  registered (optional, since it can be added later), and check that a UK number has a valid format (GB followed by 9 digits, or 12
  digits for branch traders).
- **FR-006**: System MUST ask the user to confirm before saving a change to currency or VAT,
  stating that the change affects only new quotes and invoices.
- **FR-007**: System MUST keep a record of every currency/VAT settings change (old value, new
  value, date and time) so that it's always possible to tell which settings were in force on
  a given date.
- **FR-008**: System MUST display every money amount using the selected currency's symbol and
  exactly two decimal places. Changing the currency MUST NOT convert any stored amounts.
- **FR-009**: Settings MUST persist across restarts and work with no internet connection.
- **FR-010**: System MUST provide a "price entry mode" setting with two options: "prices
  include VAT" (the default) and "prices exclude VAT". The mode decides how prices typed into
  FloorPro are interpreted. Changing the mode MUST require confirmation and MUST NOT change
  the value of any price already stored. Mode changes MUST be recorded in the settings history
  (FR-007).

**Customer records**

- **FR-011**: Staff MUST be able to create a customer with: title (optional), first name, last
  name, company name (optional), mobile phone, other phone, email, address (lines 1–2,
  town/city, county, postcode), notes, and contact preferences (whether the customer agrees to
  receive marketing messages).
- **FR-012**: A customer MUST have either a person's name (first or last) or a company name,
  and MUST have at least one phone number or an email address.
- **FR-013**: System MUST give each customer a unique, permanent, human-readable reference
  (e.g. C-00042) that's never reused, even after deletion.
- **FR-014**: System MUST check email addresses for a valid format and store UK postcodes in
  standard upper-case format with a single space.
- **FR-015**: System MUST warn staff about possible duplicates when a new customer's phone
  number or email, or an edited one, matches an existing customer, and let them open the existing record or save
  anyway.
- **FR-016**: Staff MUST be able to search customers by any part of the name, company name,
  phone number (ignoring spaces and punctuation), email, postcode, or customer reference. The
  results MUST update as they type.
- **FR-017**: The customer list MUST be sortable by name, reference and date added, and MUST
  hide archived customers unless "show archived" is turned on.
- **FR-018**: Staff MUST be able to edit any customer field. The system MUST record when each
  customer was created and last updated.
- **FR-019**: Staff MUST be able to archive and restore customers, with confirmation before
  archiving.
- **FR-020**: Staff MUST be able to export all data held about a single customer to a
  human-readable file.
- **FR-021**: Staff MUST be able to erase a customer after a confirmation step that requires
  typing the customer's name (either the person's name or the company name). Customers with
  no linked records are permanently deleted.
  Customers with linked financial records have their personal details anonymised while those
  records are kept.
- **FR-022**: The customer record screen MUST include a space where later features will list
  that customer's jobs, orders, appointments and invoices, with an empty-state message until
  those features exist.
- **FR-023**: Every save, archive and erase action MUST give immediate visible confirmation,
  and every validation failure MUST show a plain-English message next to the relevant field.
- **FR-024**: Customer data MUST be stored only on the shop's own computer and be available
  with no internet connection.

**Customer types and VAT display**

- **FR-025**: Every customer MUST have a type, either domestic or trade. New customers default
  to domestic. Staff MUST be able to change the type at any time.
- **FR-026**: Every customer MUST have a "show VAT breakdown" preference. It defaults to off for
  domestic customers. For trade customers it MUST be on and can't be turned off.
- **FR-027**: When a customer changes from domestic to trade, the VAT breakdown preference MUST
  switch on and lock. When a customer changes from trade to domestic, the preference MUST stay
  on until staff turn it off.
- **FR-028**: The customer list MUST show each customer's type and MUST be filterable by type
  (all, domestic, trade).
- **FR-029**: The company/trading name field MUST be clearly offered for trade customers. It
  remains optional for both types (a sole-trader fitter may be recorded by their own name).

### Key Entities *(include if feature involves data)*

- **Business Settings**: The single set of business-wide values: currency (code and symbol),
  whether the business is VAT registered, VAT rate, VAT registration number, and price entry
  mode (include or exclude VAT). There's exactly one current set.
- **Settings Change Record**: A history entry for each currency or VAT change: which setting
  changed, old value, new value, and when. Used to show what was in force at any date.
- **Customer**: A person or business the shop deals with. Holds the customer reference, type
  (domestic or trade), "show VAT breakdown" preference, name and/or company name, contact
  details, address, notes, marketing consent, active/archived status, and created/updated
  dates. Future jobs, orders, appointments and invoices will link
  to a customer.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A member of staff can add a new customer with name, phone and address in under
  60 seconds.
- **SC-002**: With 10,000 customers stored, search results appear within 1 second of typing,
  and the right customer is found from any single search term (name, phone, postcode, email or
  reference).
- **SC-003**: A first-time user can find and change the VAT rate in under 30 seconds without
  help.
- **SC-004**: 100% of attempts to save invalid data (missing name, no contact method, VAT rate
  outside 0–100%) are blocked with a message that names the problem.
- **SC-005**: After a restart, 100% of saved settings and customer details are exactly as they
  were left.
- **SC-006**: Every money amount shown in the app uses the selected currency symbol and two
  decimal places.
- **SC-007**: In testing with shop staff, at least 9 out of 10 can add, find and edit a
  customer on their first attempt without guidance.
- **SC-008**: Staff can tell at a glance, from the customer list, whether any customer is
  domestic or trade, and can filter to either group in one click.

## Assumptions

- FloorPro is used in UK flooring shops. Addresses and postcodes follow UK formats, and VAT
  registration numbers follow the UK format.
- There's a single VAT rate for the business in this feature. Reduced or zero-rated items
  (e.g. some energy-saving installations) are out of scope and can be added with quoting and
  invoicing.
- User logins and per-staff permissions are out of scope. Anyone using the shop computer can
  view and edit customers and settings.
- Other business details for invoices (shop name, address, logo, bank details, invoice
  numbering) are out of scope here and belong to the invoicing feature.
- Each customer has one main address. Separate installation/site addresses belong to the
  future jobs feature, since one customer (e.g. a landlord) may have work done at many
  addresses.
- This feature only stores each customer's type and VAT display preference. Actually
  producing VAT-inclusive or VAT-breakdown quotes and invoices belongs to the quoting and
  invoicing features. Those features will also let staff override the preference on an
  individual document (e.g. one insurance quote for an otherwise normal domestic customer).
- Trade pricing, discounts, credit limits, payment terms and trade account numbers are out of
  scope here. They'll build on the customer type in later features.
- Importing customers from another system or spreadsheet is out of scope for this feature.
- The currency list covers common currencies only. FloorPro never converts between
  currencies.
- Financial records that block permanent deletion don't exist yet. Until they do, every
  erase is a permanent deletion, but the anonymise rule is specified now so later features
  respect it.
