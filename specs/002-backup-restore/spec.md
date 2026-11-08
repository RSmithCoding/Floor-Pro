# Feature Specification: Backup and Restore

**Feature Branch**: `main` (no feature branch created)

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "backup and restore of the shop's data"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Back up now (Priority: P1)

The shop owner wants a safe copy of everything in FloorPro: customers, settings and their
history, and everything later features add. From a Backups screen they press **Back up now**.
Within seconds FloorPro confirms the backup was made and lists it with its date, time and size.

**Why this priority**: This is the core protection against losing the shop's data. The
constitution makes backup and restore a release blocker (Principle I).

**Independent Test**: Add some customers, press **Back up now**, and confirm a new backup
appears in the list, shows the right date, and can be opened by the restore feature with every
customer intact.

**Acceptance Scenarios**:

1. **Given** the Backups screen, **When** the user presses **Back up now**, **Then** a complete
   backup is created, a confirmation is shown, and the backup appears at the top of the list
   with its date, time, size, type ("Manual") and how many customers it contains.
2. **Given** staff are using FloorPro on another screen at the same moment, **When** a backup
   is made, **Then** it captures a consistent snapshot and nobody's work is interrupted.
3. **Given** the backup destination can't be written to (e.g. a USB drive was unplugged or the
   disk is full), **When** a backup is attempted, **Then** the user sees a plain-English error
   saying what went wrong, and no partial backup file is left behind.

---

### User Story 2 - Restore from a backup (Priority: P1)

Something has gone wrong: records were deleted by mistake, or the computer's data is damaged.
The owner opens the Backups screen, picks a backup, sees what it contains and when it was made,
confirms, and FloorPro goes back to exactly that state.

**Why this priority**: A backup is only useful if it can be restored, simply and safely, by a
non-technical person under pressure.

**Independent Test**: Back up, change and delete some customers, restore the backup, and
confirm every customer and setting is exactly as it was when the backup was made.

**Acceptance Scenarios**:

1. **Given** a list of backups, **When** the user chooses **Restore** on one, **Then** they see
   its date, type and contents (customer count), a clear warning that everything changed since
   then will be replaced, and must confirm by typing `RESTORE` before anything happens.
2. **Given** the user confirms a restore, **When** it runs, **Then** FloorPro first makes a
   "Before restore" backup of the current data, then replaces the data with the chosen backup,
   and shows "Restored the backup from 3 Nov 2026, 17:30". The restored data appears straight
   away, with no restart.
3. **Given** a restore fails part-way (for example the backup file turns out to be damaged),
   **When** that happens, **Then** the shop's current data is left exactly as it was and the
   user is told the backup couldn't be used.
4. **Given** the user restored the wrong backup, **When** they look at the list, **Then** the
   "Before restore" backup is there, so they can undo the restore by restoring that.

---

### User Story 3 - Automatic backups (Priority: P2)

Most shops won't remember to back up. FloorPro makes a backup automatically every day the app
is used, keeps a sensible number of them, and warns if backups have stopped working.

**Why this priority**: Protects shops that never press **Back up now**. It depends on the
backup mechanism from User Story 1.

**Independent Test**: Use FloorPro on several different days (simulated) and confirm one
automatic backup per day appears, older automatic backups beyond the retention limit are
removed, and manual backups are never removed automatically.

**Acceptance Scenarios**:

1. **Given** FloorPro is opened for the first time on a given day, **When** it starts, **Then**
   an automatic backup is made in the background without slowing the user down.
2. **Given** more automatic backups exist than the retention limit, **When** a new one is made,
   **Then** the oldest automatic backups are deleted. Manual, "Before restore" and "Before
   upgrade" backups are not affected by this rule.
3. **Given** the most recent successful backup is more than 7 days old, or the last automatic
   backup failed, **When** the user opens the dashboard, **Then** a warning card says so and
   links to the Backups screen.
4. **Given** the Backups screen, **When** the user turns automatic backups off, **Then** no more
   are made and the dashboard shows a reminder that automatic backups are off.

---

### User Story 4 - Keep a copy away from the computer, and move to a new computer (Priority: P2)

A backup stored on the same computer won't help if that computer is stolen, breaks or catches
fire. The owner chooses where backups are kept. They can also take a backup file to a new
computer, including from a Mac to a Windows PC, and restore it there to carry on where they
left off.

**Why this priority**: Off-computer copies are what make backups survive real disasters. Moving
to a new computer is the same restore mechanism applied to a file from elsewhere.

**Independent Test**: Choose a backup folder on another drive, make a backup and confirm the
file is there. Copy that file to a fresh FloorPro install on another computer, restore it, and
confirm all data appears.

**Acceptance Scenarios**:

1. **Given** the Backups screen, **When** the user chooses a backup folder (for example a USB
   drive, or a OneDrive, Dropbox or iCloud Drive folder), **Then** every new backup, manual and
   automatic, is saved there, and the screen shows the chosen folder.
2. **Given** the Backups screen, **When** the user chooses **Save a copy to…** on any backup,
   **Then** they pick a place with the computer's normal Save dialog and a copy of that backup is
   saved there, still password-protected.
3. **Given** a backup file from another computer, **When** the user chooses **Restore from a
   file…**, picks it and enters its backup password, **Then** FloorPro checks it is a genuine
   FloorPro backup and restores it as in User Story 2.
4. **Given** a backup made on a Mac, **When** it is restored on Windows (or the other way round),
   **Then** all data is restored identically.

---

### User Story 5 - Password-protected backups (Priority: P1)

Backups contain customers' names, addresses and phone numbers, and may be kept on a USB stick
or in a cloud folder. Every backup is protected with a backup password, so a lost USB stick or
a shared cloud folder doesn't expose anyone's details.

**Why this priority**: The shop has data-protection obligations (Principle I), and backups are
designed to travel off the computer. Protection has to be in place before the first backup.

**Independent Test**: Set a backup password, make a backup, and confirm the file can't be read
without the password: opening it in another program shows no customer details, and restoring it
on another computer works only with the correct password.

**Acceptance Scenarios**:

1. **Given** no backup password has been set, **When** the user opens the Backups screen,
   **Then** they're asked to set one first: entered twice, at least 10 characters, with a clear
   warning that a forgotten password means those backups can never be restored, and advice to
   write it down and keep it somewhere safe away from the computer.
2. **Given** a password is set, **When** FloorPro makes manual or automatic backups on this
   computer, **Then** it doesn't ask for the password each time.
3. **Given** a backup made on this computer with the current password, **When** it is restored
   here, **Then** no password is asked for. **Given** a backup from another computer or made with
   an older password, **When** it is restored, **Then** its password must be entered.
4. **Given** the user wants a new password, **When** they change it (entering the current one
   first), **Then** new backups use the new password, and they're told that existing backups
   still need the password they were made with.

---

### Edge Cases

- **Backup from a newer FloorPro version**: restoring is refused with "This backup was made by a
  newer version of FloorPro. Update FloorPro first." Current data is untouched.
- **Backup from an older FloorPro version**: it is restored, then upgraded to the current
  version automatically (with the usual pre-upgrade backup).
- **File that isn't a FloorPro backup, or is damaged**: refused with a clear message before
  anything is changed.
- **Damaged data at startup** (deferred from feature 001): if FloorPro can't open the shop's
  data when it starts, it doesn't crash. It shows a recovery screen offering to restore the most
  recent backup, after setting the unreadable data aside rather than deleting it.
- **Backup location unavailable** (USB drive not plugged in, network or cloud folder offline):
  automatic backups fall back to FloorPro's own data folder and the dashboard warning says the
  chosen location couldn't be reached.
- **Very large data** (years of records): backups and restores still complete; a progress
  indicator is shown if it takes more than a couple of seconds.
- **Two backups in the same second**: both are kept, with distinct names.
- **Deleting a backup**: allowed from the list after confirmation. The most recent successful
  backup can't be deleted.
- **Forgotten backup password**: backups protected with it can't be restored by anyone,
  including FloorPro's makers. The password screen says this plainly when it's set.
- **Wrong password** when restoring: "That password doesn't open this backup." Nothing changes,
  and the user can try again.
- **Backup made with an older password** (after the password was changed): FloorPro asks for
  that backup's password when restoring it.
- **No backup password set yet**: no backups can be made (except the built-in "Before upgrade"
  copies, see FR-031), and the dashboard shows "Set a backup password to start backing up".

## Requirements *(mandatory)*

### Functional Requirements

**Making backups**

- **FR-001**: System MUST provide a Backups screen, reachable from the main navigation.
- **FR-002**: Users MUST be able to make a backup on demand with **Back up now**.
- **FR-003**: A backup MUST contain all of the shop's data held by FloorPro (customers,
  settings, settings history, and any data later features add), so that restoring it alone
  fully recreates the shop's records.
- **FR-004**: A backup MUST be a consistent snapshot, even if FloorPro is being used while it
  is made.
- **FR-005**: A backup MUST be written completely or not at all. A failed backup leaves no
  partial file and shows a plain-English error.
- **FR-006**: Each backup MUST record when it was made, its type (Manual, Automatic, Before
  restore, Before upgrade), the FloorPro version and data version that made it, and a summary
  of its contents (at least the number of customers).
- **FR-007**: The Backups screen MUST list all backups, newest first, showing date and time
  (local), type, size, customer count and location.
- **FR-008**: Backups made automatically before database upgrades (existing behaviour) MUST
  appear in the list as "Before upgrade".

**Restoring**

- **FR-009**: Users MUST be able to restore any listed backup, or a backup file chosen from
  anywhere on the computer (**Restore from a file…**).
- **FR-010**: Before restoring, the system MUST show the backup's date, type and contents, warn
  that all changes since then will be replaced, and require the user to type `RESTORE` to
  confirm.
- **FR-011**: Before replacing any data, the system MUST make a "Before restore" backup of the
  current data. If that backup can't be made, the restore MUST NOT go ahead.
- **FR-012**: A restore MUST be all-or-nothing: if it fails at any point, the current data stays
  exactly as it was.
- **FR-013**: The system MUST check a backup is a genuine, undamaged FloorPro backup before
  restoring, and refuse anything else with a clear message.
- **FR-014**: The system MUST refuse backups made by a newer FloorPro version, and MUST upgrade
  backups from older versions after restoring them.
- **FR-015**: After a successful restore, the restored data MUST be shown immediately without
  restarting FloorPro, with a confirmation naming the backup's date and time.
- **FR-016**: Backups made on macOS MUST restore on Windows and vice versa, with identical data.

**Automatic backups and retention**

- **FR-017**: When automatic backups are on (the default), the system MUST make one automatic
  backup on the first start of FloorPro each calendar day, without delaying the user.
- **FR-018**: The system MUST keep the 14 most recent automatic backups and delete older
  automatic ones. Manual, Before restore and Before upgrade backups MUST NOT be deleted by this
  rule (Before upgrade backups keep their existing limit of 10).
- **FR-019**: Users MUST be able to turn automatic backups on or off.
- **FR-020**: The dashboard MUST show a warning card when the last successful backup is more
  than 7 days old, the last automatic backup failed, the chosen location couldn't be reached,
  or automatic backups are turned off. The card links to the Backups screen.
- **FR-021**: Users MUST be able to delete a backup after confirmation, except the most recent
  successful one.

**Location**

- **FR-022**: Users MUST be able to choose a backup folder anywhere the computer can write to
  (including USB drives and cloud-synced folders). All new backups are saved there. Until a
  folder is chosen, backups are saved in FloorPro's own data folder.
- **FR-023**: Users MUST be able to save a copy of any listed backup to a place they choose with
  **Save a copy to…**, using the computer's normal Save dialog.
- **FR-024**: If the chosen backup location is unavailable, automatic backups MUST fall back to
  FloorPro's own data folder and record that the fallback happened.

**Recovery at startup**

- **FR-025**: If FloorPro can't open the shop's data at startup, it MUST show a recovery screen
  instead of crashing. The screen offers to restore the most recent backup and explains what
  happened. The unreadable data MUST be moved aside, never deleted.

**Protection**

- **FR-026**: Every backup file MUST be protected with the shop's backup password, so its
  contents can't be read or restored without that password.
- **FR-027**: A backup password MUST be set before the first backup. It must be entered twice,
  be at least 10 characters, and the user must be warned that a forgotten password can't be
  recovered.
- **FR-028**: FloorPro MUST remember what it needs to make and restore backups on this computer
  without asking for the password each time. The password itself MUST NOT be stored in a form
  that can be read back and shown.
- **FR-029**: Restoring a backup made elsewhere or with a different password MUST require that
  backup's password. A wrong password MUST change nothing and say so.
- **FR-030**: Users MUST be able to change the backup password after entering the current one.
  New backups use the new password; existing backups keep the one they were made with.
- **FR-031**: The automatic "Before upgrade" backups (existing behaviour) MUST stay in
  FloorPro's own data folder and never be copied elsewhere automatically. Once a backup password
  is set they MUST be protected the same way as other backups.

### Key Entities *(include if feature involves data)*

- **Backup**: A complete copy of the shop's data at a moment in time. Attributes: when it was
  made, type (Manual, Automatic, Before restore, Before upgrade), FloorPro version and data
  version, size, location, and a contents summary (customer count). Lives as a file, so it
  can be copied to other drives or computers.
- **Backup preferences**: Whether automatic backups are on, the chosen backup folder, whether a
  backup password has been set (never the password itself), when the last backup succeeded or
  failed, and any fallback that happened.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With 10,000 customers, **Back up now** completes in under 10 seconds.
- **SC-002**: With 10,000 customers, a restore completes, including its safety backup, in under
  30 seconds.
- **SC-003**: In testing, 100% of restores reproduce the backed-up data exactly (every record
  and setting matches).
- **SC-004**: In fault-injection testing (damaged files, interrupted restores, unwritable
  destinations), 0 cases leave the shop's current data changed or partially restored.
- **SC-005**: A first-time user can restore a chosen backup in under 2 minutes without help.
- **SC-006**: A backup made on macOS restores successfully on Windows, and vice versa.
- **SC-007**: Automatic backups never delay opening FloorPro by more than 1 second.
- **SC-008**: In testing, 0 backup files reveal any customer name, phone number, email or
  address when opened without the password.

## Assumptions

- Backups are whole-shop: there is no restoring of individual customers or records. (Exporting
  one customer already exists for data-protection requests.)
- Only one computer runs FloorPro for a shop's data at a time. Sharing one database between
  several tills or PCs is out of scope.
- No user accounts exist yet, so anyone using the shop computer can back up and restore. The
  typed `RESTORE` confirmation guards against accidents.
- The backup password protects backup files *away from* the shop computer (USB drives, cloud
  folders, a stolen drive). It doesn't protect the shop computer itself: anyone who can use
  FloorPro on that computer can make and restore backups.
- There is no password recovery. A forgotten password means the backups made with it are lost;
  new backups can be started with a new password.
- "Contents summary" shows the customer count now; later features add their own counts (jobs,
  invoices) to the summary.
- Automatic retention is 14 daily backups, and the "no recent backup" warning triggers at 7 days.
  These are fixed in this feature; making them configurable can come later.
- FloorPro does not upload anything to the internet itself. Off-computer copies rely on a
  folder the user chooses (or saves to), which may itself be synced by a cloud service the shop
  already uses.
- Restoring replaces the data in place without restarting; any screens open at the time show
  the restored data on their next action.
