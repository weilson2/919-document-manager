# Milestone progress

## M0 · Project Foundation

**Status:** ACCEPTED on 18 November 2026.

The workspace already contained an independent POS application, its database, and backups. The Document Manager lives in a new sibling directory with its own Git history and local data location.

### Implementation plan and acceptance criteria

| Step | Acceptance criterion |
| --- | --- |
| Establish project layout and dependency versions | The package installs on 64-bit CPython 3.12 and dependency verification passes. |
| Build the desktop shell | All ten navigation entries reach the expected pages and Company Settings can be opened from the Dashboard. |
| Initialize storage through Alembic | A new data directory gets a migrated SQLite database, the initial company, and a log. Reopening the directory preserves saved edits. |
| Add the settings workflow | The initial company identity is displayed, validated on save, and reflected on the Dashboard. The schema accepts multiple distinct companies. |
| Apply local failure handling | A failed migration rolls back. A corrupt or unrecognized database is preserved and startup reports a failure. |
| Verify release inputs | Run the automated tests and dependency check, build the source distribution and wheel, and smoke-test startup from the installed wheel. |
| Close M0 | Record limitations and manual acceptance here, then commit M0 for review. |

### Verification completed

- Windows 11 x64, Python 3.12.14, SQLite 3.53.1, and PySide6 6.12.0. Qt WebEngine and Qt WebChannel imports succeeded.
- All nine tests passed, covering migrations, settings persistence and validation, the ten navigation destinations, and startup failure handling.
- Dependency and lint checks passed. The source distribution and wheel built successfully. The development launcher and the installed wheel each initialized a separate test workspace.
- Dashboard and Company Settings were visually inspected using offscreen Qt rendering with Windows Segoe UI. The user confirmed interactive Windows 11 acceptance for base commit `8071d77`.

### Major technical risks

- **SQLite migration safety.** Startup acquires a write lock before reading the Alembic revision and wraps the revision and seed in one transaction. Future migrations that transform live data will need backup and restore tests.
- **Embedded editor isolation.** M2 will need local bundled assets, denied remote navigation, a restricted WebChannel, and tests for both untrusted template input and local file access.
- **Pagination and Unicode exports.** M2–M3 will need reproducible page breaks, a shared print model, and testing with Chinese, English, and Malay fonts on installed Windows systems.
- **Historical integrity.** Later milestones will need published template versions and finalized document snapshots that remain stable through profile edits and template upgrades.
- **Payroll correctness.** M5 will need verified, versioned statutory schedules and blocked approvals when the applicable rule configuration is missing or unverified.
- **Windows distribution.** WebEngine helpers, Qt plugins, local assets, fonts, and license notices will need fresh-install verification before release.

### Manual acceptance

1. Follow the README setup. Start with an unused test folder using `.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-acceptance"`.
2. Verify that the Dashboard shows **919 RESTAURANT** and that each sidebar entry opens the corresponding page. Use **Ctrl+1** to return to the Dashboard and **Ctrl+,** to open Company Settings.
3. Clear the company name and select **Save changes**. Verify the validation message. Enter a different name and a multiline address, save, and confirm the Dashboard shows the new name.
4. Close and reopen using the same data folder. Confirm the saved changes persist. Verify that `document-manager.sqlite3` and `application.log` exist there.
5. Run `.\.venv\Scripts\python.exe -m document_manager --check --data-dir "$env:TEMP\919-document-manager-acceptance"` and expect a success message and exit code `0`.

### Current limitations

- Dashboard and Company Settings are functional. The other navigation destinations are placeholders.
- Multiple company records are supported by the schema. Company creation and profile switching are scheduled for M1.
- Authentication, roles, audit history, encrypted backups, and the Windows installer are later work. The development workspace is for evaluation with sample data.

## M1 · Dashboard and Business Data

**Status:** ACCEPTED on 18 November 2026.

### Delivered

- Dashboard counts, company-specific recent activity, and quick actions for tenants, employees, and templates.
- Company creation and switching, saved startup default, profile contacts, local logo import and storage, and default page settings.
- Tenant and employee forms, search and filters, archiving and restoration, and exact MYR storage.
- Template categories and metadata, duplication and archiving, and immutable published metadata versions. The Document Editor page links to Templates.

### Technical plan and migration risks

- Revision `0002_business_data` adds profile columns and company-scoped tables within the existing startup transaction. It preserves the M0 company rows and saved company selection. A downgrade discards M1 data, so downgrade checks belong on disposable databases.
- Repositories constrain reads and writes by company ID. Composite foreign keys enforce company membership for template categories and versions. Record changes and activity entries commit in the same transaction.
- Financial input is checked for range and fractional sen before persistence. SQLite stores the exact integer amount, including zero, and rejects fractional values in money columns.
- Archived records retain their identifiers and business status. Duplicate checks include archived rows so a restored record keeps its original identity.
- Published versions carry template metadata and a slot for the future structured document. SQLite rejects updates, deletes, and replacements of published version rows. Editing current metadata changes its status to Draft and keeps the published history.

### Verification completed

- All 28 tests passed on Windows 11 x64 for implementation commit `82a814b`. Coverage includes the M0 upgrade, SQLite constraints, company isolation, duplicate and invalid inputs, archive recovery, restart persistence, and desktop workflows.
- Dependency and lint checks passed. The source distribution and wheel built successfully.
- The installed 0.2.0 wheel opened a fresh workspace and upgraded a workspace created with the installed M0 wheel. The edited M0 profile survived the upgrade.
- The user confirmed manual Windows 11 acceptance. M1 screens were also inspected with Qt's offscreen renderer.
- Follow-up commit `b09e145` covers direct startup instructions and dropdown readability. The regression suite passed all 29 tests after that change.

### Manual acceptance

1. Launch M1 against a copy of an accepted M0 workspace or use a fresh folder with `.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-m1"`. Verify that the existing or seeded company opens and that the ten sidebar destinations open.
2. Edit contact information, choose a PNG or JPEG logo, and change the company page size or margins. Save. Add a second company and use **Make default** there. Switch through the sidebar and verify the settings differ between companies.
3. Create a tenant using Dashboard **New tenant**. Open the identification, rental type, and status lists and verify that each option is readable. Test search and filters, then edit the deposit. Create an employee including optional payroll attributes and check the salary-type list. Try a duplicate employee number and a MYR value of `12.345`; both should be rejected.
4. Archive a tenant and an employee. Verify their dashboard counts decrease, then open their **Archived** filters and restore them. Switch companies and verify that the original records, counts, and activity only appear in the original company.
5. In **Templates**, create a category and template, assign the category, publish the metadata, rename the template, then publish again. Duplicate the template and verify that the copy is a draft. Archive and restore it. Open **Document Editor** to verify the placeholder.
6. Close and reopen the same workspace. Verify the default company opens and saved details, records, and template states persist.

### Current limitations

- The Dashboard shows an unavailable state for generated documents. The template editor, document generation, exports, and payroll calculations are later milestones.
- Recent activity covers business changes in the current company. Local authentication, role controls, encrypted backups, and production packaging are later milestones.

## M2.1 · Editor Foundation

**Status:** ACCEPTED on 18 November 2026.

### Delivered

- Embedded Tiptap 3 and ProseMirror in the existing Document Editor page. The installed wheel includes the JavaScript, CSS, HTML, and third-party notices. The editor reads Qt's WebChannel script from a Qt resource and serves it at the editor's local origin.
- Added a WebChannel object with one application slot. Its dispatcher handles session open and document verification. The desktop selects the company and assigns a session ID. A company switch closes the previous session and opens a blank editor for the new company.
- Added version 1 of the wire protocol and paragraph document schema. Both sides validate the structured data. The editor's off-the-record profile permits only the named local assets and blocks external navigation and local file URLs.
- Kept the M0/M1 database schema and migrations in place. The editor does not write drafts or versions in M2.1.

### Verification completed

- All 56 tests passed on Windows 11 x64 for implementation commit `b39b672`, including the 29 M0/M1 regression tests. The user confirmed manual Windows 11 acceptance.
- Two subprocess tests started real Qt WebEngine renderers from source and from an installed wheel. Both verified the WebChannel handshake, exact Unicode and paragraph structure, blocked navigation, and a fresh session on company switch.
- The wheel was installed with pip's index disabled and opened without Node/npm on PATH. The renderer ran offscreen with GPU acceleration disabled, DNS resolution blocked, and a loopback-only proxy. The editor enforced its normal URL allowlist.
- TypeScript type checking, bundle reproducibility, Python dependency and lint checks, and the Python source distribution and wheel builds passed.

### Windows 11 manual acceptance

1. From the `919_DOCUMENT_MANAGER` project directory, start a separate workspace with `.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-m21"`. Disconnect from the network for the offline check.
2. Select **Document Editor** and wait for **Editor ready**. Type `Perjanjian sewa — 麻坡`, add a blank paragraph, and type `Lot 12 & 13`. Select **Verify document**. Expect **Document structure verified** and confirm the text and blank paragraph remain visible.
3. Create a second company in **Company Settings**. Open **Document Editor** for it and confirm the editor starts blank. Switch back to the first company and confirm it opens with a fresh editor.
4. Close and reopen the app. Confirm the company profiles still exist and Document Editor starts with a blank page.

### Current limitations

- The foundation handles plain text and paragraphs. It applies size limits and keeps edits only in the current company session.
- The visual editing panels, formatting, pagination, dynamic fields, and draft and publish workflows are planned for M2.2 through M2.4.

## M2.2 · Visual Editing

**Status:** ACCEPTED on 18 November 2026.

### Delivered

- Added the editing toolbar, outline, insertion and page navigation, A4/A5 canvas, and properties inspector.
- Added rich text, headings, lists, editable tables, local images, font and color controls, paragraph spacing and alignment, zoom, shortcuts, and undo/redo.
- Page guides and preview sheets are calculated from layout. Breaks keep text lines, table rows and row spans, and figures intact where the available page size allows. Oversized content stays visible and triggers a warning.
- Added visual document schema version 2. The original version 1 session and verification contract remains available. Image import uses the company-bound bridge, a native file picker, PNG/JPEG validation, and a managed local asset directory.

### Verification completed

- All 66 tests passed on Windows 11 x64 for implementation commit `1834301` and after the image resizing follow-up `2e7c794`. The real Qt renderer tests exercised formatting and keyboard input, editable tables, valid and invalid images, Unicode serialization, multi-page layout, zoom stability, preview, and blocked network and cross-company image requests. The follow-up also verified drag resizing, exact width entry, and undo/redo.
- The installed-wheel renderer also passed with pip's index disabled, Node/npm removed from PATH, and external networking disabled for the browser probe.
- TypeScript checks, bundle reproducibility, Python lint and dependency checks, and the source distribution and wheel builds passed.

### Windows 11 manual acceptance results

The user reported **Overall PASS**, with all nine checks passing.

| 验收项目 | 结果 |
| --- | --- |
| 合同中英文文字完整 | PASS |
| A4 多页分页正常 | PASS |
| 调整 Zoom 不改变分页 | PASS |
| 字体、字号、对齐正常 | PASS |
| 薪水单表格可增加/删除行列 | PASS |
| Undo / Redo 正常 | PASS |
| Logo 插入和调整正常 | PASS |
| Preview 返回后内容完整 | PASS |
| 没有程序崩溃或严重错误 | PASS |

### Windows 11 manual acceptance steps

1. From `919_DOCUMENT_MANAGER`, launch with `.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-m22"` and open **Document Editor**.
2. Type a heading and some Unicode text. Check the outline, apply bold, italic, underline, font size, text color and spacing, and use **Ctrl+Z** to undo a change.
3. Insert a table, edit cells, and add and delete a row and column. Open **Preview** after adding enough text and rows for several pages. Use the page list and change zoom. Verify that the logical page breaks stay in place and that rows and text are visible.
4. Change paper size, orientation, and margins. Insert a PNG or JPEG, select it, and drag its bottom-right resize handle. Undo the drag, then enter an exact width and description in the **Image** panel. Try a tall image and check that an oversized warning appears while the image remains visible. An SVG or invalid image should be rejected.
5. Select **Verify document** and expect **Document structure verified**. Switch companies and confirm that the new editor opens blank. Repeat with the network disconnected to confirm offline startup.

### Current limitations

- Preview uses Chromium's measured layout and has been verified for the cases above. It is a visual preview for this editor.
- Undo/redo applies to document content and formatting. Page setup is adjusted separately. Documents remain temporary, and imported asset files remain in the company workspace.
- Dynamic fields, draft persistence, publishing, and final PDF export are future milestones.

## M2.3 · Dynamic Fields

**Status:** Awaiting Windows 11 manual acceptance.

- Added the field library, inline references, and a properties form for the twelve field types.
- Version 3 stores definitions in a separate field registry and uses stable IDs on inline nodes. Versions 1 and 2 remain available through the bridge. Unsupported versions, unsupported rules, duplicate keys, and missing references are rejected.
- The ProseMirror history covers field creation, edits, insertion, and deletion. A definition can be deleted when it has no document references.
- Fields and document edits belong to the temporary company session. The required flag, validation, defaults, and formatting are definition metadata for later form generation.

### Verification completed

- The Windows 11 automated suite passed 92 Python tests, including the M0–M2.2 regressions and native Qt renderer coverage of creation, insertion, reuse, formatting, rename, deletion, undo/redo, and company switching.
- The offline test opened the installed wheel in Qt WebEngine with Node/npm removed from PATH and external networking disabled for the browser probe.
- Three TypeScript validation tests passed. Type checking, bundle reproducibility, Python lint and dependency checks, and the source distribution and wheel builds passed.

### Windows 11 manual acceptance

1. Open a separate workspace with `.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-m23"`, then open **Document Editor**.
2. Choose **New field**, enter the key `rent_amount` and label `月租 · Rent`, select **Currency (MYR)**, and set the default to `120.005`. Verify Save rejects it. Change it to `120.50`, select an RM display format, and save.
3. Insert the field twice. Click one occurrence, rename its key and label, and save. Check that both labels update and that Undo and Redo restore both. Try saving a second definition with the same key, and try deleting the referenced definition. Both should be rejected.
4. Remove the two inline references, then delete the definition and undo that deletion. Select **Check structure** and expect **Document structure verified**.
5. Disconnect from the network, reopen the separate workspace, and repeat a field insertion. Switch companies to confirm the new session opens with an empty field list.

## Integrated release

The integrated program started at `04f26a6`. M2.2 passed 66 automated tests and nine interactive Windows 11 checks. The preserved baseline passed 92 Python tests, including the offline wheel probe.

- [x] WP1. Page breaks, headers, footers, page numbering, cell merge/split, and print layout regression tests.
- [x] WP2. Integer, decimal and record reference fields, record binding, and conditional paragraphs.
- [x] WP3. Autosaved drafts, stale-save detection, immutable publishing, and version comparison in Templates.
- [x] WP4. Schema-driven forms with company-scoped record selection, overrides, and Design Mode round trips.
- [x] WP5. One resolved PDF pipeline for preview and export. A4 portrait, A5 landscape, Chinese and Malay, images, and multipage tables are exercised in Qt.
- [x] WP6. Searchable, immutable document snapshots with checksum verification, deferred PDF loading, export tracking, archiving, and reuse.
- [x] WP7. Ten editable starter designs and a separate fictional acceptance workspace.
- [x] WP8. Decimal draft payroll, effective-dated schedule boundaries, auditable adjustments, revision snapshots, and draft payslips. Final approval is blocked pending verified statutory adapters.
- [x] WP9. Local sign-in and roles, encrypted backup and clean-folder restore, PyInstaller build configuration, and x64 Windows MSI authoring.
- [x] WP10. Automated rental, offer, draft payslip, and custom-template journeys through Qt with the Windows manual checklist below.

### Release verification

| Check | Result |
| --- | --- |
| Python regression suite | 101 passed, including M0/M1 migration preservation, stale drafts, roles, contribution boundaries, immutable history, encrypted backup/restore, and the four Qt journeys. |
| Editor checks | Seven TypeScript tests passed. Type checking and the checked-in bundle comparison passed. |
| Python build and dependencies | Ruff and `pip check` passed. The source distribution and wheel built successfully. An offline installed-wheel probe repeated all four Qt journeys. |
| Print output | A4 portrait dimensions, margins, Chinese and Malay text, image placement, headers, footers, and page numbers passed. An A5 landscape table retained all 120 test rows across 12 pages. |
| Windows packaging | The PyInstaller executable and WiX x64 MSI built. Windows Installer extracted the MSI into a new test folder. The extracted executable generated three PDFs offline, reopened its database, and passed SQLite integrity and PDF checksum verification. A full interactive install remains part of the manual checklist. |

The build now excludes generic ICU DLLs from the build machine PATH so Qt can load the Windows ICU libraries it was built against. [Windows ICU API](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-)

The artifacts are `dist/919DocumentManager-0.4.0rc1-x64.msi` and `dist/python-0.4.0rc1/`. The MSI SHA-256 is `4688D352E7716B6AF3A6484B97566D01F46865290EAD1B0C27CF910DDE7A38BC`.

### Release limitations

- Statutory payroll approval stays blocked while verified EPF, SOCSO, EIS and PCB/MTD adapters are unavailable. The draft calculations show the missing amounts and exclude them from estimated totals.
- The release includes password-protected backups. The live workspace and exported copies rely on Windows filesystem protection.
- Design canvas page guides are approximate. The Fill Mode PDF preview is the export source. Font coverage depends on the installed Windows fonts.
- Starter wording and signature lines are editable illustrations. The package is unsigned.

### Integrated release Windows 11 manual acceptance

1. Install the x64 MSI and launch the sample workspace with the [README command](README.md#windows-11-acceptance). Create a test owner account. Verify the active company begins with **DEMO** and the dashboard shows two tenants, two employees, and three saved documents. Test offline.
2. **Rental agreement.** Choose **New Rental Agreement**, select Fictional Tenant A, and verify the name, identification, stall, rent, deposit, and start date. Add a line of additional terms. Preview the A4 PDF, save it in History, and export it. Select the saved record using its document number and choose **Reuse values**. Change the rent, then preview and save. Open the original and verify its rent and document number stayed the same.
3. **Employee offer.** Choose **New Offer Letter**, select Fictional Employee A, and check the name, position, monthly basic salary, and start date. Enter probation, working hours, and notice. Choose **Edit design**, adjust a clause, publish, return to the filled values, and choose the newer version. Save and export the resulting offer letter. Search History by the employee name.
4. **Draft payslip.** Choose **New Payslip**, select Fictional Employee A and a payroll month, and add earnings and an advance. Calculate the draft. Check the gross and estimated net amounts against those entries. Verify **Check approval** names the missing rules and blocks approval. Save a draft revision, preview the draft payslip, and save it to History. Load the draft as a new revision, change an amount, and verify the first revision and PDF are unchanged.
5. **Custom document.** Open Templates, choose **New template**, then **Edit design**. Add a heading, table, and local PNG or JPEG. Create a required currency field, insert it twice, and apply an optional paragraph condition to a second field. Insert a page break and enable a page number. Publish the design. Fill it, confirm `15.001` is rejected, then use `15.25`. Inspect the print preview, save and export. Reuse the captured values from History.
6. Restart using the same sample directory and confirm template drafts, published versions, history, and payroll revisions persist. Sign in as a test clerk and confirm payroll and employee history are restricted.
7. Sign back in as owner. Create and verify an encrypted backup. Restore it into a new folder, open the restored workspace, and check that the company, records, PDF exports from History, and managed images are available.

Manual Windows 11 release acceptance is pending. Automated verification uses a separate fictional workspace.

## 0.4.1 RC1 offer letter form

Fill Mode uses a light form surface, larger labels, and readable validation text under the Windows dark palette. The Employee Offer Letter explains the probation period and gives examples for working hours and notice period. Published starter versions display the same guidance at runtime. Entries and published version data are preserved.

The native Windows rendering was checked with the dark palette. All 103 Python tests passed, including contrast and guidance checks for current and older starter versions.

The x64 MSI built and extracted into a fresh test folder. The extracted app included the updated help text and started offline in a fictional workspace. The installer is available at `dist/919DocumentManager-0.4.1rc1-x64.msi`.

