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

M2.3 is pending implementation approval.

