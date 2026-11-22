# 919 Document Manager

An offline Windows workspace for designing business templates, filling documents from company records, generating PDFs, keeping history, and preparing draft payroll.

## Install and open

Use the x64 MSI from the release build on Windows 10 version 1809 or later, or Windows 11. Open **919 Document Manager** from the Start menu. On the first launch, create the local owner account with a password of at least 12 characters. The app includes the Python and Qt runtimes. It runs offline and uses a locally bundled editor.

For a source checkout, install 64-bit CPython 3.12 and run the following from the project folder. The CMD launcher works from PowerShell with script execution disabled.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,packaging]"
.\Start-DocumentManager.cmd
```

The live workspace typically resides in `%LOCALAPPDATA%\919 Document Manager`. It contains a SQLite database, a rotating log, and managed template images. Alembic applies migrations in a transaction and preserves earlier profiles and template metadata versions. A new regular workspace opens as **919 RESTAURANT**. Company settings supply registration, address, contact information, logo, and document defaults. Use the sidebar selector to switch companies.

To initialize or check an isolated workspace, use `.\Start-DocumentManager.cmd --check --data-dir "$env:TEMP\919-check"`. For installed copies, use the same arguments with `919DocumentManager.exe`. The application log records startup errors.

## Design, fill, and file documents

1. Open **Templates**. Select a starter or choose **New template**. Ten starter designs are installed per company. The guides and clauses are editable illustrations. Review them for suitability before official use.
2. Choose **Edit design**. The editor autosaves the draft and checks for conflicting saves. **Save draft** or **Ctrl+S** saves on demand. **Publish design** creates an immutable version. **Versions** shows publication dates and design or field changes.
3. Select **Create document**. Choose a tenant or employee when a design uses a record binding. You can add a new record from this form, or override a prefilled value for this document. Required fields are marked with an asterisk.
4. Choose **Preview PDF**, inspect the actual PDF, and select **Save to history**. **Export PDF** writes the saved bytes to the selected location. **Back to form** retains your entries. **Edit design** pauses the form and **Return to filled values** resumes it. If a newer design exists, you can keep the current version or carry matching fields forward.
5. Open **History** to find a document by number, title, or subject. View and export the original PDF, or use **Reuse values** to start a new document from the original version and inputs. Changing the company, tenant, employee, or template leaves the original PDF and captured data intact. Use the **Archived** filter to restore archived records.

In an offer letter, **Probation period** is the initial time for reviewing a new employee’s performance before deciding on confirmation. Enter the agreed duration with its unit, such as **3 months** or **12 weeks**.

### Editing and field design

The editor supports flowing text, headings, lists, formatting, tables, images, and explicit page breaks. For a table merge, select multiple cells, then use **Merge cells**. Select an image and drag its corner, or set its percentage width in **Image**. PNG and JPEG imports accept up to 8 MB and 4096 × 4096 pixels. Page setup includes A4 or A5, portrait or landscape, margins, repeated plain-text headers and footers, page numbers, and the company logo. Use at least 8 mm of top or bottom margin for the corresponding running text or numbers.

Choose **New field**, enter its key and label, and select **Save field settings**. Place the cursor or select text, then choose **Insert field**. Repeated placements share the same field definition. Define separate fields for independent values, such as rent and deposit. Click a placeholder to edit its field settings. For conditional text, select a paragraph and set **Show paragraph when filled**. Remove inline and conditional references before deleting a field. Undo and Redo work for field definitions and placements.

Fields cover text, multiline text, integer, decimal, MYR currency, date, date range, dropdown, checkbox, boolean, phone, email, address, and tenant, employee, or company references. **Prefill from** selects a supported record property. Fill Mode enforces the field type and configured bounds. Amounts typed directly into a design remain ordinary text.

The sidebar **Document Editor** opens a temporary canvas until you select a template. In Design Mode, **Preview** shows guides for editing placeholders. For resolved content and final page placement, use **Preview PDF** from Fill Mode. The application uses the same PDF bytes for Fill Mode preview, history, and export. Pagination and available glyphs depend on installed Windows fonts. Layout can differ from Microsoft Word.

## Payroll

Open **Payroll**, choose the employee and month, and enter earnings, advances, and authorized deductions. The page loads monthly basic salary. Enter period basic pay explicitly for daily or hourly employees. **Calculate draft** shows gross pay, known deductions, estimated net pay, employer cost, and each contribution's status. Draft manual amounts require a reason and are recorded with each saved revision.

Select **Save draft revision** and **Preview payslip**, then save or export the clearly marked draft PDF. **Load as new revision** lets you correct values while retaining earlier snapshots. Use **Check approval** to verify that the application blocks final approval and names the unavailable rules. The release contains no verified statutory calculation adapters for EPF, SOCSO, EIS, or PCB/MTD. Missing contributions remain unknown, and draft totals exclude them. Official schedules for future verification are available from [KWSP](https://www.kwsp.gov.my/en/epf-act-1991-third-schedule), [PERKESO](https://www.perkeso.gov.my/en/our-services/employer-employee/contributions.html), and [HASiL](https://www.hasil.gov.my/en/majikan/jadual-pcb-dan-spesifikasi-data/).

## Local access and recovery

- Owners can add local owner, payroll officer, and clerk accounts. Owners and payroll officers can access employees, payroll, and employee-linked documents. Owners manage company settings and backups. Restart the program to switch signed-in users.
- Passwords use salted scrypt hashes. Backup archives use password-derived AES-256-GCM encryption. The live SQLite database, managed images, and PDF files exported outside the app use the protection of the Windows account and filesystem.
- In **Backup & Restore**, select **Create encrypted backup** and choose a separate password. The app takes a consistent SQLite snapshot and includes referenced template images and saved PDFs. Use **Verify backup file** to check the archive, database, and files. Backups support workspaces up to 256 MB before compression. Keep the password so you can restore the archive.
- Choose **Restore to a new workspace** to verify and extract a copy into an unused folder. Then choose **Open restored workspace** and sign in with an account from the backup. The current workspace remains available until you close it.

## Windows 11 acceptance

Use a new fictional workspace. The sample command requires an unused directory and seeds a fictional company, two tenants, two employees, an agreement, an offer, a draft payslip, and a published custom template.

```powershell
$demo = Join-Path $env:TEMP ("919-demo-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
.\Start-DocumentManager.cmd --sample --data-dir "$demo"
```

For the MSI, run the installed `919DocumentManager.exe` with the same arguments. After creating the sample workspace, omit `--sample` when reopening it. See [the four Windows acceptance journeys](PROGRESS.md#integrated-release-windows-11-manual-acceptance).

## Development and packaging

| Component | Responsibility |
| --- | --- |
| `src/document_manager/ui/` | PySide6 desktop pages, safe embedded editor, Qt WebEngine printing, and Qt PDF preview |
| `src/document_manager/editor/` and `editor/` | Pydantic JSON validation, restricted WebChannel, Tiptap 3/ProseMirror, and the checked-in offline assets |
| `src/document_manager/services/` | Scoped document, template, fill, payroll, access, and backup workflows |
| `src/document_manager/payroll.py` | Exact Decimal calculations and effective-dated contribution schedule handling |
| `src/document_manager/persistence/` | SQLAlchemy 2.x repositories, SQLite constraints, and Alembic migrations |
| `src/document_manager/presets/` | Editable source data for the ten starter designs |
| `tests/` | pytest, pytest-qt, offline installed-wheel probes, and the four automated Qt journeys |

PySide6 provides the Windows shell and bundled browser and PDF engines. SQLAlchemy and Alembic manage SQLite and explicit migrations. Pydantic validates templates and form input, and `cryptography` handles authenticated backup encryption. The wheel packages the data and assets. PyInstaller bundles the Windows runtime. WiX builds the MSI. Node, TypeScript, and esbuild are development tools for the editor bundle.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build --no-isolation
npm.cmd --prefix editor ci --ignore-scripts
npm.cmd --prefix editor test
npm.cmd --prefix editor run build
npm.cmd --prefix editor run check:bundle
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm 919DocumentManager.spec
$bundle = (Resolve-Path .\dist\919DocumentManager).Path
wix build -arch x64 -bindpath "app=$bundle" -out .\dist\919DocumentManager-x64.msi .\installer\919DocumentManager.wxs
```

Use WiX 5.0.2 or compatible for the build command. The Qt tests require an environment that allows Chromium child processes. The installed-wheel probe runs with Node and npm removed from PATH and browser networking blocked. Backups and packaging tests use isolated workspaces.
