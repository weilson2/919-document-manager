# Milestone progress

## M0 · Project Foundation

**Status:** Awaiting acceptance.

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
- Dashboard and Company Settings were visually inspected using offscreen Qt rendering with Windows Segoe UI. Interactive desktop acceptance on Windows 10 and 11 is pending.

### Major technical risks

- **SQLite migration safety.** Startup acquires a write lock before reading the Alembic revision and wraps the revision and seed in one transaction. Future migrations that transform live data will need backup and restore tests.
- **Embedded editor isolation.** M2 will need local bundled assets, denied remote navigation, a restricted WebChannel, and tests for both untrusted template input and local file access.
- **Pagination and Unicode exports.** M2–M3 will need reproducible page breaks, a shared print model, and testing with Chinese, English, and Malay fonts on installed Windows systems.
- **Historical integrity.** Later milestones will need published template versions and finalized document snapshots that remain stable through profile edits and template upgrades.
- **Payroll correctness.** M5 will need verified, versioned statutory schedules and blocked approvals when the applicable rule configuration is missing or unverified.
- **Windows distribution.** WebEngine helpers, Qt plugins, local assets, fonts, and license notices will need fresh-install verification before release.

### Manual acceptance

1. Follow the README setup. Start with an unused test folder using `.\Start-DocumentManager.ps1 -DataDir "$env:TEMP\919-document-manager-acceptance"`.
2. Verify that the Dashboard shows **919 RESTAURANT** and that each sidebar entry opens the corresponding page. Use **Ctrl+1** to return to the Dashboard and **Ctrl+,** to open Company Settings.
3. Clear the company name and select **Save changes**. Verify the validation message. Enter a different name and a multiline address, save, and confirm the Dashboard shows the new name.
4. Close and reopen using the same data folder. Confirm the saved changes persist. Verify that `document-manager.sqlite3` and `application.log` exist there.
5. Run `.\Start-DocumentManager.ps1 -Check -DataDir "$env:TEMP\919-document-manager-acceptance"` and expect a success message and exit code `0`.

### Current limitations

- Dashboard and Company Settings are functional. The other navigation destinations are placeholders.
- Multiple company records are supported by the schema. Company creation and profile switching are scheduled for M1.
- Authentication, roles, audit history, encrypted backups, and the Windows installer are later work. The development workspace is for evaluation with sample data.

M1 is pending M0 acceptance.
