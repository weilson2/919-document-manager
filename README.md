# 919 Document Manager

Offline-first Windows desktop software for Malaysian SME document administration. M0 provides the desktop navigation, local database, and editable company identity.

## Run on Windows

Use 64-bit CPython 3.12 on Windows 10 version 1809 or later, or Windows 11. Run these PowerShell commands from the `919_DOCUMENT_MANAGER` directory. If the Python launcher is unavailable, replace `py -3.12` with your Python 3.12 executable.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m document_manager
```

After setup, the development launcher also accepts `-DataDir` to use a separate workspace and `-Check` to initialize and check storage without opening a window.

```powershell
.\Start-DocumentManager.ps1
.\Start-DocumentManager.ps1 -Check -DataDir "$env:TEMP\919-document-manager-dev"
```

Initial dependency installation uses PyPI. The installed application runs locally without a server or network connection.

## Local data and startup

By default, the database and rotating log are stored in Qt's per-user application data directory, typically `%LOCALAPPDATA%\919 Document Manager` on Windows. To inspect the exact database path, run:

```powershell
.\.venv\Scripts\python.exe -m document_manager --check
```

Startup applies the packaged Alembic revisions within a SQLite transaction. The initial migration seeds 919 RESTAURANT and selects it as the active company. Edit its name, registration number, or address in **Company Settings**. Use **Ctrl+1** for the Dashboard and **Ctrl+,** for Company Settings.

On startup failure, the error message identifies the log location when available. An unrecognized, unversioned database is rejected. Use a separate `--data-dir` to diagnose a startup issue while preserving the original workspace.

## Project layout

| Location | Responsibility |
| --- | --- |
| `src/document_manager/app.py` | Startup, local paths, logging, and application lifetime |
| `src/document_manager/ui/` | PySide6 shell, navigation, company settings |
| `src/document_manager/services/` | Application workflows and validated settings |
| `src/document_manager/persistence/` | SQLAlchemy models, SQLite, and packaged Alembic migrations |
| `tests/` | Automated database, startup, and desktop tests |

As later milestones land, `src/document_manager/domain/` will hold document, business-data, and payroll rules. `src/document_manager/rendering/` will own document resolution and export adapters. `editor/` will house the TypeScript/Tiptap editor and build its local Qt WebEngine assets. Windows packaging will live in `packaging/`. Business workflows will call the domain and persistence from the service layer. Editor messages will cross a validated Qt WebChannel boundary.

## Dependencies

| Dependency | Reason |
| --- | --- |
| PySide6 6.12.0 | Qt Widgets desktop shell, with Qt WebEngine and Qt WebChannel available for later milestones. [Qt Windows support](https://doc.qt.io/qt-6.12/windows.html) |
| SQLAlchemy 2.0.58 and Python SQLite | Typed models, transaction management, and embedded storage. [SQLAlchemy release](https://pypi.org/project/SQLAlchemy/2.0.58/) |
| Alembic 1.20.1 | Explicit schema revisions and migration/model consistency checks. [Alembic](https://pypi.org/project/alembic/1.20.1/) |
| Pydantic 2.14.3 | Validates and normalizes company input at the service boundary. [Pydantic](https://pypi.org/project/pydantic/2.14.3/) |
| pytest 9.2.0 and pytest-qt 4.5.0 | Exercise startup, databases, and actual Qt widget interactions. |
| setuptools 84.2.1 and build 1.6.1 | Build the source distribution and wheel, including migrations. |

## Tests and build

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m build
```

SQLite tests use temporary workspaces. Desktop tests use Qt's offscreen platform by default. If building offline with the declared build backend already installed, pass `--no-isolation` to `python -m build`.

Schema changes require an Alembic revision under `src/document_manager/persistence/migrations/versions`. The `migration_config` context manager supplies Alembic with a connection to an explicitly selected database. Use a disposable development database for revision generation or downgrade checks.

See [PROGRESS.md](PROGRESS.md) for M0 acceptance steps and current limitations.
