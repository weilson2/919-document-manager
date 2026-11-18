# 919 Document Manager

Offline-first Windows desktop software for Malaysian SME document administration. M2.1 adds the local visual editor foundation to the company profiles, tenant and employee registers, and template tools delivered in M1.

## Run on Windows

Use 64-bit CPython 3.12 on Windows 10 version 1809 or later, or Windows 11. Run these PowerShell commands from the `919_DOCUMENT_MANAGER` directory. If the Python launcher is unavailable, replace `py -3.12` with your Python 3.12 executable.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m document_manager
```

Use `--data-dir` to open a separate workspace. Add `--check` to initialize and check storage without opening a window. These commands can run from PowerShell with script execution disabled.

```powershell
.\.venv\Scripts\python.exe -m document_manager --data-dir "$env:TEMP\919-document-manager-dev"
.\.venv\Scripts\python.exe -m document_manager --check --data-dir "$env:TEMP\919-document-manager-dev"
```

Initial dependency installation uses PyPI. The installed application runs locally without a server or network connection.

## Local data and startup

By default, the database and rotating log are stored in Qt's per-user application data directory, typically `%LOCALAPPDATA%\919 Document Manager` on Windows. To inspect the exact database path, run:

```powershell
.\.venv\Scripts\python.exe -m document_manager --check
```

Startup applies the packaged Alembic revisions within a SQLite transaction. A fresh database opens as 919 RESTAURANT. Opening an M0 workspace preserves its company records and default company. Use **Ctrl+1** for the Dashboard and **Ctrl+,** for Company Settings.

On startup failure, the error message identifies the log location when available. An unrecognized, unversioned database is rejected. Use a separate `--data-dir` to diagnose a startup issue while preserving the original workspace.

## Using M1

- **Dashboard** shows non-archived template totals, active tenant and employee counts, recent changes, and shortcuts for creating records. Generated-document totals become available with document generation.
- **Company Settings** manages identity, contact details, logo, and document defaults for A4 or A5, orientation, and margins. Use **New company** to add a profile, the sidebar to switch companies for this session, and **Make default** to select the company that opens on startup. Logos accept PNG or JPEG files up to 2 MB and 2048 × 2048 pixels. The application stores a normalized PNG in the database.
- **Tenants** records identification, contact details, stall, rental frequency, MYR rent and deposit, start and end dates, and status. **Employees** records staff and contact details, employment information, basic salary, and optional payroll eligibility attributes. Enter dates as `YYYY-MM-DD` and money with up to two decimal places. Amounts are stored as integer sen and handled as `Decimal` in Python.
- **Templates** lets you create and assign categories, create and edit template metadata, duplicate it as a draft, and archive it. **Publish metadata** retains an immutable numbered snapshot. Changes to published metadata create a draft while retaining earlier snapshots.
- **Archive** hides a record from the working list. Open **Archived**, select the record, and use **Restore** to recover it with its previous business status. Identifiers remain reserved while archived. Tenant and employee identification numbers are checked by identification type within the company. Employee numbers, template names, and category names are unique within the company. Company registration numbers are checked across profiles.

Company switching scopes business records and activity within the local workspace. Local sign-in and role-based access are later milestones. M1 captures payroll inputs and template metadata. Rendering, payroll calculations, and backup tooling remain scheduled for later milestones.

## Trying the local editor

Open **Document Editor** in the sidebar, wait for **Editor ready**, and enter several paragraphs. Select **Verify document** to check that the editor's structured JSON survives a round trip through Python.

The editor uses bundled Tiptap 3 and ProseMirror in an off-the-record Qt WebEngine profile. Its request policy permits only named editor assets under a local URL scheme. The dedicated WebChannel object accepts two operations, session open and document verification. Python binds the session to the selected company. Both sides validate the versioned document and protocol payloads.

M2.1 supports plain text and paragraphs in a temporary editor. Switching companies or closing the app discards the content. Later subphases add formatting, page layout, dynamic fields, and template persistence.

## Project layout

| Location | Responsibility |
| --- | --- |
| `src/document_manager/app.py` | Startup, local paths, logging, and application lifetime |
| `src/document_manager/ui/` | PySide6 shell, dashboard, company and record screens |
| `src/document_manager/editor/` | Editor document schema, WebChannel bridge, and bundled WebEngine assets |
| `editor/` | TypeScript editor sources, pinned npm lockfile, and bundle build |
| `src/document_manager/services/` | Input validation, company settings, and transactional business workflows |
| `src/document_manager/persistence/` | SQLAlchemy models, company-scoped repositories, SQLite, and packaged Alembic migrations |
| `tests/` | Automated database, migration, service, startup, and desktop tests |

As later milestones land, `src/document_manager/domain/` will hold document, business-data, and payroll rules. `src/document_manager/rendering/` will own document resolution and export adapters. Windows packaging will live in `packaging/`. Business workflows will call the domain and persistence from the service layer.

## Dependencies

| Dependency | Reason |
| --- | --- |
| PySide6 6.12.0 | Qt Widgets desktop shell, with Qt WebEngine for the local editor and Qt WebChannel for its validated bridge. [Qt Windows support](https://doc.qt.io/qt-6.12/windows.html) |
| SQLAlchemy 2.0.58 and Python SQLite | Typed models, transaction management, and embedded storage. [SQLAlchemy release](https://pypi.org/project/SQLAlchemy/2.0.58/) |
| Alembic 1.20.1 | Explicit schema revisions and migration/model consistency checks. [Alembic](https://pypi.org/project/alembic/1.20.1/) |
| Pydantic 2.14.3 | Validates and normalizes company input at the service boundary. [Pydantic](https://pypi.org/project/pydantic/2.14.3/) |
| pytest 9.2.0 and pytest-qt 4.5.0 | Exercise startup, databases, and actual Qt widget interactions. |
| setuptools 84.2.1 and build 1.6.1 | Build the source distribution and wheel, including migrations. |
| Tiptap 3.34.0 and ProseMirror | Schema-driven editing and document JSON. [Tiptap schema](https://tiptap.dev/docs/editor/core-concepts/schema) |
| Node 24, TypeScript 6.0.3, and esbuild 0.28.2 | Developer tools for type checking and bundling the offline editor. [esbuild bundling](https://esbuild.github.io/api/#bundle) |

## Tests and build

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
```

SQLite tests use temporary workspaces. Desktop tests use Qt's offscreen platform by default. If building offline with the declared build backend already installed, pass `--no-isolation` to `python -m build`.

The WebEngine tests start real Chromium renderers in subprocesses. The wheel test builds and installs the package locally with pip's index disabled, removes Node/npm from the renderer's PATH, and runs with a loopback-only proxy, disabled DNS resolution, and the normal editor request policy. Run these tests in an environment that allows Chromium's renderer process to start.

Rebuild the checked-in JavaScript, CSS, and dependency notices after changing the editor source. From the project directory, run:

```powershell
npm.cmd --prefix editor ci --ignore-scripts
npm.cmd --prefix editor run build
npm.cmd --prefix editor run check:bundle
```

The npm install may require registry access. Runtime startup and Python package builds use the checked-in bundle.

Schema changes require an Alembic revision under `src/document_manager/persistence/migrations/versions`. The `migration_config` context manager supplies Alembic with a connection to an explicitly selected database. Use a disposable development database for revision generation or downgrade checks.

See [PROGRESS.md](PROGRESS.md) for the M2.1 Windows acceptance checklist and current limitations.
