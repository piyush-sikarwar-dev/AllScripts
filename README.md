# Legacy DEC & LR Records

A read-only web viewer for the retired Allscripts system. Clinic staff find a patient, see the full
record and export it as a PDF for a records release. It covers the EHR (EMR), practice management
(Ntier) and the pre-2010 chart (DMZ).

Stack: Python 3.12, FastAPI, Jinja2 + HTMX, SQL Server (read-only, via ODBC 18), PostgreSQL 16
for the app's own data, WeasyPrint for PDFs.

| Read next | For |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Full specification: architecture, rules, design system |
| [docs/DATA_MAP.md](docs/DATA_MAP.md), [docs/DATA_INVENTORY.md](docs/DATA_INVENTORY.md) | What each database holds; every table and column the app reads |
| [docs/PRE2010_RECORDS.md](docs/PRE2010_RECORDS.md) | The separate pre-2010 section |
| [docs/SECURITY.md](docs/SECURITY.md) | Security controls and status |
| [docs/RUNBOOK.md](docs/RUNBOOK.md), [docs/DEPLOYMENT_PLAN.md](docs/DEPLOYMENT_PLAN.md) | Deploying to EC2 / AWS |

---

## Getting started (local development)

There are two ways to run the app:
- **A. Fake data:** clearly fake patients, no SQL Server needed. Start here.
- **B. Real archive:** the Allscripts SQL Server, read-only.

Both need the app's own PostgreSQL database.

### 1. Install the tools (once)

| Tool | Why | How |
|---|---|---|
| **Git** | Get the code | https://git-scm.com |
| **uv** | Installs Python 3.12 and the exact locked dependencies | Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` · macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **PostgreSQL 16** | The app's own database (users, sessions, audit and release logs). The migrations use PostgreSQL features, so SQLite won't work. | Docker Desktop (step 4), **or** a local / portable PostgreSQL 16 on port **5433** |
| *Only for B:* **Microsoft ODBC Driver 18 for SQL Server** | Connects to the archive | https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server |
| *Only for PDF export:* **Pango / GTK libraries** | Needed by WeasyPrint | Linux / Docker: system packages. Windows without admin rights: see [PDF export on Windows](#pdf-export-on-windows). |

### 2. Get the code and dependencies
```sh
git clone https://github.com/Centricity-Research/Legacy-DEC-LR-Records.git
cd Legacy-DEC-LR-Records
uv sync                      # creates .venv with Python 3.12 + locked packages
```

### 3. Create your `.env` (local settings, never committed)
Create a file named `.env` in the project folder. Minimum for **fake data**:
```ini
USE_FAKE_DATA=true
APP_DATABASE_URL=postgresql+psycopg://legacy:legacy-dev-only@127.0.0.1:5433/legacy_viewer
SESSION_SECRET=any-long-random-text-for-local-use-only-0123456789
COOKIE_SECURE=false          # local http only; production is always true
CLINIC_NAME=Example Clinic
CLINIC_TZ=America/New_York
FEATURE_LEGACY_DMZ=true      # shows the "Pre-2010 records" section
```
`.env` is git-ignored. Never put real passwords in `.env.example` or any committed file.

### 4. Start PostgreSQL and create the tables
```sh
docker compose up -d postgres            # PostgreSQL 16 on 127.0.0.1:5433 (user legacy / legacy-dev-only)
uv run python -m alembic upgrade head    # creates the app's tables
```
(With your own PostgreSQL instead: create database `legacy_viewer` and a user, then match
`APP_DATABASE_URL`.)

### 5. Create your sign-in account
```sh
uv run python cli.py create-user --email you@example.org --name "First Last"
```
You're prompted for the password twice (minimum 12 characters). There is no sign-up page.

### 6. Run it
```sh
uv run uvicorn app.main:app --reload
```
Open **http://127.0.0.1:8000**, sign in, and browse the fake patients (clearly invented names such as
"Sample, Patient A"). Every tab, the pre-2010 section, printing and the PDF export work on fake data.

---

### B. Using the real archive (read-only)

Add these to `.env` and switch fake data off:
```ini
USE_FAKE_DATA=false
SQL_HOST=<sql server host>
SQL_PORT=1433
SQL_USER=<read-only login>
SQL_PASSWORD=<password>
SQL_TRUST_SERVER_CERTIFICATE=false   # true only if the server has no trusted certificate
EMR_DATABASE=EMR
NTIER_DATABASE=Ntier_0010060
DMZ_DATABASE=DMZ
```
Then:
```sh
uv run python cli.py dbcheck           # connection, versions, login permissions (metadata only)
uv run python cli.py build-crosswalk   # links EMR <-> PM patients into the app database (a few minutes)
uv run uvicorn app.main:app --reload
```
Notes:
- **Read-only by design.** Every statement is checked by `app/db/readonly.py` (only a single
  `SELECT` is allowed), and the login should have only `db_datareader`. Never run write queries
  against the archive.
- **Scanned pages** need a copy of the file shares. Until then the Documents tab lists them and
  shows a banner. Set `SCAN_ROOT` / `LEGACY_SCAN_ROOT` to the copies (docs/RUNBOOK.md, Part F).
- **No PHI outside the app:** don't paste patient data into tickets, chat or logs.

---

## Everyday commands

| Task | Command |
|---|---|
| Run with auto-reload | `uv run uvicorn app.main:app --reload` |
| Lint + format check + unit tests | `uv run ruff check . && uv run ruff format --check . && uv run pytest -m "not integration"` |
| Auto-format | `uv run ruff format . && uv run ruff check --fix .` |
| Integration tests (real archive) | `RUN_INTEGRATION=1 uv run pytest -m integration` (needs ODBC 18 + access) |
| New migration after changing `app/repositories/appdb/models.py` | `uv run python -m alembic revision --autogenerate -m "what changed"` then `upgrade head` |
| Add a staff account | `uv run python cli.py create-user --email E --name N` |
| Reset a password / disable an account | `cli.py reset-password --email E` · `cli.py deactivate-user --email E` |
| Rebuild patient links | `uv run python cli.py build-crosswalk` |

The same commands are in the `Makefile` (`make dev`, `make test`, `make lint`, `make format`).

## Project layout (short)

```
app/
  sql/{emr,ntier,dmz}/*.sql   one read-only query per file
  repositories/               runs the SQL (live.py = real data, legacy.py = pre-2010)
  services/                   turns rows into view models for each screen
  routers/                    pages and HTMX fragments
  templates/ static/          Jinja2 + HTMX, one stylesheet (app.css)
config/*.yaml                 code labels and settings that aren't in the database
tests/fakes/                  the fake patients used by tests and USE_FAKE_DATA
docs/                         data map, inventory, security, deployment
```

Rules worth knowing before changing code (full list in CLAUDE.md):
- **Queries:** explicit columns only; never select the SSN / password columns; one query per `.sql`
  file with bound parameters.
- **Fakes:** every repository function has a fake in `tests/fakes/`, so tests run without any
  database.
- **CSS:** no inline styles (the Content-Security-Policy blocks them); every style is a class in
  `app.css`.
- **Before every commit:** `ruff` + unit tests must pass.

## PDF export on Windows

WeasyPrint needs Pango. Without admin rights:
1. Download the MSYS2 base archive and unpack it to `%LOCALAPPDATA%\msys64`.
2. In its shell, run `pacman -S mingw-w64-ucrt-x86_64-pango`.
3. In `.env`, set `WEASYPRINT_DLL_DIRECTORIES=%LOCALAPPDATA%\msys64\ucrt64\bin`.

Without it the app still runs; only the PDF export (and its tests, which are then skipped) needs
it.

## Troubleshooting

| Problem | Fix |
|---|---|
| `connection refused` on 5433 | PostgreSQL isn't running: `docker compose up -d postgres` |
| `relation "users" does not exist` | Run `uv run python -m alembic upgrade head` |
| Signed out after every click | `COOKIE_SECURE=false` is needed for plain `http://` locally |
| `Data source name not found` / ODBC error | Install ODBC Driver 18, or use `USE_FAKE_DATA=true` |
| App refuses to start: "unsafe production configuration" | You set `APP_ENV=production` locally; remove it (production checks are in docs/SECURITY.md §2.6) |
| PDF export error about Pango / `gobject` | See [PDF export on Windows](#pdf-export-on-windows) |
