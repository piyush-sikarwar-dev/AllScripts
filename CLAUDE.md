# CLAUDE.md — Legacy Records Viewer

Permanent project context for Claude Code. Read this file fully before every task.
Build phase by phase from `BUILD_PROMPTS.md`; never start a later phase unasked.

---

## 1. What we are building

A **read-only web viewer for a retired Allscripts EHR**. The clinic lost access to the
Allscripts application; the SQL Server databases were restored to AWS. Staff need to
find a patient and see their full record (visits, notes, problems, medications, labs,
vitals, documents) and export it as a PDF to release medical records.

- **Users:** 5 clinic staff, all with the **same single role** (no role management).
- **Flow:** Sign in → Dashboard / patient list (sidebar) → click a patient → patient chart with tabs.
- **Data is never written back.** The source databases are read-only. Only our own
  small app database is writable (users, sessions, audit log, release log, crosswalk).
- **The data is PHI (HIPAA).** Every chart view and export is audit-logged. No PHI in
  application logs, error messages, URLs' query strings beyond IDs, or test fixtures.

---

## 2. Tech stack (fixed — do not substitute)

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Dependency mgmt | `uv` (pyproject.toml + uv.lock) |
| Web framework | FastAPI |
| HTML | Jinja2 templates rendered server-side by FastAPI (no React, no SPA, no Flask) |
| Interactivity | HTMX 2.x, vendored into `app/static/vendor/` (no CDN) |
| CSS | One hand-written stylesheet `app/static/css/app.css` using CSS variables (Section 7). No Tailwind/Bootstrap. |
| Fonts | IBM Plex Sans (400/500/600) + IBM Plex Mono (400/500), self-hosted woff2 in `app/static/fonts/` |
| Source DB access | SQLAlchemy 2.x **Core** (`text()` queries, no ORM) over `pyodbc` + Microsoft ODBC Driver 18 for SQL Server |
| App DB | PostgreSQL 16 via SQLAlchemy 2.x **ORM** + Alembic migrations |
| Passwords | `argon2-cffi` |
| Sessions | Server-side sessions stored in the app DB; signed session-id cookie (HttpOnly, Secure, SameSite=Lax) |
| CSRF | Token per session, hidden field on every POST form, verified in a dependency |
| HTML sanitising | `nh3` (for any HTML coming out of the EMR) |
| PDF | WeasyPrint (HTML → PDF) + `pypdf` / `img2pdf` for appending scanned pages |
| Settings | `pydantic-settings` (env vars / `.env`) |
| Tests | `pytest`, `httpx` TestClient; integration tests marked `@pytest.mark.integration` |
| Lint/format | `ruff` (lint + format) |
| Run | `uvicorn` (dev), `gunicorn -k uvicorn.workers.UvicornWorker` (prod), Docker |

---

## 3. Architecture

```
Browser ── HTML (Jinja2) + HTMX partial swaps
   │
FastAPI
   ├─ middleware: security headers · session · audit log · request id
   ├─ routers/       pages (full pages) and partials (HTMX tab/search fragments)
   ├─ services/      one per chart area; merges sources, decodes codes, formats dates,
   │                 sets a `source` label on every record ("EMR" | "PM" | "Pre-2010")
   ├─ crosswalk/     resolves a patient key → {emr_id, ntier_id, dmz_id}
   ├─ lookups/       code → label maps (loaded at startup, cached)
   ├─ repositories/  emr/ · ntier/ · dmz/   (read-only SQL, one function per query)
   │                 appdb/                  (ORM: users, sessions, audit, releases, crosswalk)
   └─ sql/           emr/*.sql · ntier/*.sql · dmz/*.sql   (one query per file)
        │
        ├─ SQL Server: EMR            (current clinical chart)
        ├─ SQL Server: Ntier_0010060  (practice management: accounts, insurance, appointments)
        ├─ SQL Server: DMZ            (pre-2010 legacy chart, migration staging)
        └─ PostgreSQL: app DB         (our own data)
```

### Folder layout

```
legacy-viewer/
 ├─ app/
 │   ├─ main.py              app factory, lifespan (load lookups, warm caches)
 │   ├─ config.py            Settings (pydantic-settings)
 │   ├─ db/
 │   │   ├─ source.py        engines for EMR / Ntier / DMZ + datetimeoffset converter
 │   │   ├─ app.py           app-DB engine + session factory
 │   │   └─ sql_loader.py    load + cache .sql files as text()
 │   ├─ auth/                passwords, sessions, csrf, current_user dependency
 │   ├─ audit/               audit middleware + writer
 │   ├─ crosswalk/
 │   ├─ lookups/
 │   ├─ repositories/{emr,ntier,dmz,appdb}/
 │   ├─ services/
 │   ├─ routers/{pages.py,partials.py,auth.py,export.py,health.py}
 │   ├─ models/              Pydantic view models (what templates receive)
 │   ├─ formatting.py        dates, partial-date masks, names, ages, units
 │   ├─ sql/{emr,ntier,dmz}/*.sql
 │   ├─ templates/
 │   │   ├─ base.html  layout_app.html  layout_auth.html
 │   │   ├─ components/      macros: badge, card, table, tabs, button, input, empty_state
 │   │   ├─ pages/           login.html  dashboard.html  chart.html  release_log.html  errors/*.html
 │   │   ├─ partials/        patient_rows.html  tab_*.html  visit_detail.html
 │   │   └─ pdf/             export.html (+ print css)
 │   └─ static/{css,fonts,img,vendor}
 ├─ alembic/  alembic.ini
 ├─ cli.py                   management commands (create-user, dbcheck, build-crosswalk)
 ├─ tests/{unit,integration,fakes}
 ├─ Dockerfile  docker-compose.yml  .env.example  pyproject.toml  README.md
```

### Layer rules
- Routers never touch SQL. Services never return SQLAlchemy rows; they return Pydantic view models.
- Repositories: **one function per `.sql` file**, parameters bound (`:name`), never string-formatted SQL.
- Source repositories are synchronous (pyodbc). Services call them via
  `anyio.to_thread.run_sync` and query independent sources concurrently (`asyncio.gather`).
- Every repository function has a fake in `tests/fakes/` so unit tests run with no database.

---

## 4. Source databases — facts we verified (do not re-derive)

All three databases are on **one SQL Server instance**, reached with **one read-only login**.
Use a separate engine per database (`Database=` in the connection string), all with
`ApplicationIntent=ReadOnly`, `Encrypt=yes`, connection timeout 15 s, query timeout 30 s.

### 4.1 EMR (Allscripts Professional EHR) — schema `HPSITE`
- **21,384 patients.** Master table `HPSITE.DEMOGRAPHICS`, key **`IMREDEM_CODE`** (int).
- The same patient ID appears under **three column names** — all mean `DEMOGRAPHICS.IMREDEM_CODE`:
  - `IMREDEM_CODE`: VITALS_DATA, MESSAGE, PATIENT_CONTACTS, INSURANCES, ARCH_SCHEDULE, LABREQUISITION,
    EXTSYS_PATIENTINDEX, SCAN_DOCUMENT, TRANSCRIPTION, WEBMESSAGE, LAB_RESULT
  - `IMREDEMEC_CODE`: ENCOUNTER, LABORDERS, MEDICATIONS, PROCEDURES, DX, CHARTATTACHMENT
  - `PATIENT_ID`: HX_DIAGNOSIS, HX_MEDICATION, HTML_DOCUMENT_ORIG, PATIENT_RACE, PATIENT_ETHNICITY, PATIENT_IDENTIFIER
- Hierarchy: **Patient → ENCOUNTER (`IMREENC_CODE`) → CONTACT (`IMRECONTACT_CODE`) → clinical items**.
  Joins verified with 0 orphans.
- Other keys: `IMRENOTE_CODE` → NOTES_MASTER; `IMREPROV_CODE` → PROVIDERS; `LOCATION_ID` → LOCATION;
  `IMREADDR_CODE` → ADDRESSES (DEMOGRAPHICS.DEM_HOMEADDR); `IMRECARRIER_CODE` → INSURANCECARRIERS;
  `GUARANTOR_CODE` → DEMGUARANTOR; `DOCUMENT_ID` → SCAN_DOCUMENT / HTML_DOCUMENT_ORIG;
  `IMRELABSAMPLE_CODE` → LABSAMPLES; `IMRELABCAT_CODE` → LABCATALOG.

| Chart area | Tables (all `EMR.HPSITE`) |
|---|---|
| Demographics | DEMOGRAPHICS, ADDRESSES, PATIENT_CONTACTS, PATIENT_RACE, PATIENT_ETHNICITY, PATIENT_IDENTIFIER |
| Insurance | INSURANCES (+ INSURANCECARRIERS), DEMGUARANTOR |
| Visits | ENCOUNTER + CONTACT, ENCOUNTER_ASSESSMENT → DX, ENCOUNTER_PLAN, CHART_ADDENDUM |
| Notes | NOTES_MASTER → NOTES_TEXTDATA (NOTE_TEXT), HTML_DOCUMENT_ORIG (DOCUMENT varbinary), TRANSCRIPTION |
| Problems/allergies/history | HX_DIAGNOSIS (split by CATEGORY_CODE), HXDIAGNOSIS_ATTRIBUTES |
| Medications | MEDICATIONS (prescriptions), HX_MEDICATION (med history) |
| Labs | LAB_RESULT (+ LABORDERS, LABSAMPLES) |
| Vitals | VITALS_DATA |
| Documents | SCAN_DOCUMENT → SCAN_DOCUMENTPAGE (FILELOCATION path), SCAN_DOCUMENTTYPE |
| Lookups | PROVIDERS, LOCATION, hpsystem.DICTIONARIES_MASTER, HPSITE.DICTIONARIES_SITE, HPSITE.HISTORYCATEGORY |

### 4.2 Ntier_0010060 (Allscripts practice management) — schema `PM`
- `PM.Patients` (21,330 rows), key `Patient_ID`. `Patient_Number`, `Medical_Record_No`, `Account_ID`,
  `Contact_ID`, `Active_Patient_ID` (merge pointer). Name/DOB are NOT in PM.Patients.
- `PM.Accounts` (Account_ID), `PM.Appointments` (Patient_ID, 153,408 rows), `PM.Patient_Policies` (Patient_ID).
- **Link to EMR:** `EMR.HPSITE.EXTSYS_PATIENTINDEX.PATIENTID = Ntier_0010060.PM.Patients.Patient_Number`
  (trim both, compare with `COLLATE DATABASE_DEFAULT`). Currently matches **12,164 of 21,384** EMR patients.
  The link is **optional**: a chart must render fully with no Ntier match.

### 4.3 DMZ (pre-2010 legacy chart, migration staging)
- `conv.person` (9,868 patients, key `personkey`); `Medications.PatientMedications` (`patkey` → personkey);
  `conv.cac_chrt_header` (chart notes, `note_id`, `patkey`, `service_datetime`); `conv.cac_chrt_rtf` (note text);
  `conv.cac_results`, `conv.cac_pat_prob`, `conv.cac_pat_alrg`, `conv.cai_images`, `dbo.ScannedImages`.
- Data range 2002-01-01 → 2010-08-27.
- **No ID link to EMR is confirmed yet.** Candidates: `pat_extkey`, then name + DOB.
- Everything DMZ is behind a feature flag `FEATURE_LEGACY_DMZ` (default **off**).

### 4.4 Mandatory query rules
1. **Explicit column lists only. Never `SELECT *`.**
2. **Never select these columns:** `PROV_PASSWORD`, `PROV_SSNUM`, `DEM_SSNUM`, `GUARANTOR_SSNUM`,
   `INS_SUBSSNUM`, `EXTSYS_PATIENTINDEX.SSN`, DMZ `conv.person.ssno`, `SITES.SITE_CONNECTSTRING`,
   `SITES.SITE_LICENSEKEY`, anything in database `AIE_Master`.
3. **Latest revision only** for DX, MEDICATIONS, HX_DIAGNOSIS, HX_MEDICATION, NOTES_TEXTDATA:
   `ROW_NUMBER() OVER (PARTITION BY <item id> ORDER BY TAG_REVISION DESC) = 1`.
4. **`ARCH_*` tables are change history** — never use them for the current chart
   (exception: `ARCH_SCHEDULE` is the EMR appointment table). `ARCH_HXDIAGNOSIS` is read **only** for
   the Problems & allergies "Change history" of one entry (`sql/emr/history_changes.sql`), never for its
   current state.
5. **Visit date = `CONTACT.CON_START`.** `ENCOUNTER.ENC_DATACOLLECTIONDATE` is empty in every row.
6. **Merged patients:** `HPSITE.PATIENT_MERGE_HISTORY` (ORIGINAL_DEM_CODE → CURRENT_DEM_CODE).
   Search must not show merged-away records as separate patients; opening one redirects to the survivor.
7. **Voided rows:** hide `CONTACT.CON_CANCELED = 1`, `VITALS_DATA.VITAL_ERRONEOUS_IND = 1`,
   `TRANSCRIPTION.MARK_ERRONEOUS_DT IS NOT NULL`, `TAG_ARCHIVED = 1` (insurance) — unless a
   "show voided" toggle is on, then show them with a "Voided" badge.
8. **Partial dates:** columns ending `DATEMASK` / `DATEMASK_CODE` mark year-only or month-year dates.
   Format via `formatting.partial_date(value, mask)`. Mask values are not yet decoded: treat them via a
   config map; unknown mask → show the full date.
9. **Coded integers** (DEM_SEX, DEM_STATUS, ENC_VISITTYPE, HX_DIAGNOSIS.CATEGORY_CODE, MED_STATUS, …)
   are decoded by `lookups/`. Unknown code → `"Unknown (code N)"`, never an error.
10. **`datetimeoffset`** columns (most EMR timestamps) need a pyodbc output converter for SQL type `-155`,
    registered on every new connection (SQLAlchemy `connect` event).
11. Paginate with `ORDER BY … OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY`. Page size 25.
12. Every patient-scoped query filters on the indexed patient column; no unbounded scans per request.

### 4.5 Still unknown (build so these are configuration, not code changes)
| Unknown | How to build for it |
|---|---|
| HX_DIAGNOSIS category meanings (codes 18–39; 20, 21, 23, 24, 25 hold 97%) | `config/history_categories.yaml` mapping code → {label, group: problem/allergy/surgical/family/social}; default group "Other history" |
| Which ENC_VISITTYPE values are real visits | `config/visit_types.yaml`; visit list filter "Office visits / All entries" |
| Where the full visit note lives (HTML_DOCUMENT_ORIG vs NOTES_TEXTDATA) | Visit detail tries HTML documents linked via HTML_DOCUMENTMAP first, then NOTES_TEXTDATA text, then shows an "Note not available" empty state |
| Scanned page images (`\\amhs-db1\hmscan` share) | `DocumentStore` interface; `SCAN_ROOT` setting maps the UNC prefix to a mounted path or S3; when unset, Documents tab shows the warning banner and lists metadata only |
| Why only 57% of EMR patients link to Ntier | Crosswalk records `match_method`; patients without Ntier match simply show no PM data |

---

## 5. App database (PostgreSQL, Alembic)

| Table | Columns |
|---|---|
| `users` | id, email (unique), full_name, password_hash, is_active, failed_attempts, locked_until, created_at, last_login_at |
| `sessions` | id (random 32-byte token, stored hashed), user_id, created_at, last_seen_at, expires_at, ip, user_agent |
| `audit_log` | id, at, user_id, action (`login`,`logout`,`login_failed`,`view_patient`,`view_tab`,`view_document`,`export`,`search`), patient_key (nullable), detail jsonb (no PHI values: tab name, page, section list), ip, request_id |
| `release_log` | id, at, user_id, patient_key, sections (array), date_from, date_to, recipient (free text), page_count, file_sha256 |
| `patient_crosswalk` | patient_key (PK, e.g. `EMR:12345` / `DMZ:678`), emr_id, ntier_id, dmz_id, match_method, confidence, built_at |

Audit and release logs are append-only (no update/delete code paths).

---

## 6. Pages, routes and behaviour

| Route | Type | Purpose |
|---|---|---|
| `GET /login`, `POST /login`, `POST /logout` | page | Sign-in (layout_auth) |
| `GET /` | redirect | → `/patients` |
| `GET /patients` | page | Dashboard: totals cards + search + patient table |
| `GET /patients/rows?q=&dob=&chart=&page=` | partial | HTMX: table rows + pager (search-as-you-type, 300 ms debounce) |
| `GET /patients/{key}` | page | Patient chart: header + tab bar; Overview tab rendered server-side |
| `GET /patients/{key}/tab/{name}` | partial | HTMX tab body: overview, visits, notes, problems, meds, labs, vitals, docs |
| `GET /patients/{key}/visits/{source}/{id}` | partial | Visit detail panel |
| `GET /documents/{source}/{id}` | stream | Document content (HTML doc sanitised, or image) |
| `GET /patients/{key}/export` | partial | Export dialog (sections + date range + recipient) |
| `POST /patients/{key}/export` | file | PDF download; writes release_log + audit_log |
| `GET /release-log` | page | Paginated list of releases |
| `GET /healthz` | json | Liveness (no DB) ; `GET /readyz` checks all 4 DB connections |

- Tab switches use `hx-get` + `hx-push-url` so the URL reflects the tab (`/patients/EMR:123?tab=labs`);
  a full page load of that URL renders that tab directly (no HTMX dependency for correctness).
- All lists: newest first; empty state component when no rows; errors render a friendly partial, never a stack trace.
- `patient_key` format `EMR:<IMREDEM_CODE>` or `DMZ:<personkey>`; validate with a regex; 404 on unknown.

---

## 7. Design system (match the approved mockup exactly)

### 7.1 Tokens (`app/static/css/app.css` `:root`)
```css
--bg:#F4F6F8; --surface:#FFFFFF; --border:#DDE3E8; --row-border:#EEF1F4; --row-hover:#F2F8F8;
--ink:#17212B; --ink-2:#3A4652; --muted:#5B6875; --input-border:#C5CED6;
--accent:#0B6E73; --accent-hover:#08555A; --accent-soft:#E3F1F1; --accent-ink:#08555A;
--sidebar:#14202B; --sidebar-active:#22323F; --sidebar-text:#C9D3DC; --sidebar-muted:#9FB0BF;
--sidebar-link:#9FD8DA; --sidebar-divider:#2A3A48; --brand-icon:#7FD1D4;
--pm-bg:#E6EFFA; --pm-ink:#1F4F8A; --legacy-bg:#EEEBF8; --legacy-ink:#4A3D85;
--abn-bg:#FEF0E6; --abn-ink:#9A3A0A; --warn-bg:#FFF8E6; --warn-border:#F0D58C; --warn-ink:#6B4E00;
--panel:#F7F9FA;
--font:'IBM Plex Sans',system-ui,sans-serif; --mono:'IBM Plex Mono',ui-monospace,monospace;
--r-card:10px; --r-header:12px; --r-ctl:8px; --r-pill:999px; --ctl-h:44px;
```

### 7.2 Typography
Body 14px/1.5 `--ink`. Page title 26px/600 (chart patient name 24px/600). Section/card title 15–16px/600.
Labels 13px/500. Secondary text 13–14px `--muted`. Table headers 12px, uppercase, letter-spacing .04em, `--muted`, weight 500.
IDs (chart ID, account #) and lab values in `--mono` 13px.

### 7.3 Layout
- **App shell:** `display:flex; flex-wrap:wrap; min-height:100vh; background:var(--bg)`.
  Sidebar `flex:1 0 232px; max-width:100%`; main `flex:999 1 560px; min-width:0; padding:28px 32px 40px` (chart: 24px top);
  vertical gaps 24px (dashboard) / 18px (chart). On phones the sidebar stacks on top.
- **Sidebar** (`--sidebar`): brand row (doc-cross icon in `--brand-icon`, "Legacy Records" 15px/600 white, clinic name 12px `--sidebar-muted`),
  nav links 14px with 18px stroke icons, 11px×12px padding, radius 8px; active = `--sidebar-active` bg + white + 500;
  items: Dashboard, Patients, Release log. Footer: divider, signed-in user name (13px white), "Sign out" (13px `--sidebar-link`, POST form button styled as link).
- **Sign-in page:** two halves (`flex:1 1 420px` each). Left: `--sidebar` panel, 56/48px padding, brand, H1 34px/600 white
  "Patient records from the retired Allscripts system", 16px intro text, footer "[Clinic] · Authorized staff only".
  Right: centered card max-width 380px, padding 32px, radius 12px: "Sign in" 22px/600, Email, Password, full-width primary button 46px,
  12px note "Sessions end after 15 minutes of inactivity."

### 7.4 Components (Jinja macros in `templates/components/`)
- **Card:** surface, 1px `--border`, radius 10px, padding 16–18px.
- **Stat card:** label 13px muted · value 26px/600 · caption 12px muted. Grid `repeat(auto-fit,minmax(190px,1fr))`, gap 16px.
- **Badge (pill):** 12px, 3px×8px, radius 999px. Variants: EMR (`--accent-soft`/`--accent-ink`), PM (`--pm-bg`/`--pm-ink`),
  Pre-2010 (`--legacy-bg`/`--legacy-ink`), Abnormal flag (`--abn-bg`/`--abn-ink`, weight 600), Voided (neutral grey).
- **Buttons:** height 44px, radius 8px, 14px/500. Primary: `--accent` bg white text, hover `--accent-hover`.
  Secondary: white bg, 1px `--input-border`, `--ink`. Small (pager): height 36px, 13px.
- **Inputs:** label above (13px/500, `<label for>`), height 44px, 1px `--input-border`, radius 8px, 0×12px padding; focus outline 2px `--accent` offset 1px.
- **Table:** in a card; wide tables wrapped in `overflow-x:auto`; `border-collapse:collapse`; cells 12px padding (first/last col 16–18px);
  row top border `--row-border`; row hover `--row-hover`; card header bar (title left, count right) and pager footer.
- **Tabs:** `role="tablist"`, buttons `role="tab"` `aria-selected`, height 44px, 0×14px padding, 3px bottom border;
  active = `--accent` text + border, weight 600; inactive = `--ink-2`, transparent border. Tab bar has 1px bottom border `--border`, wraps on small screens.
- **Banner (warning):** `--warn-bg`, 1px `--warn-border`, radius 10px, 12px×16px, 14px `--warn-ink`, `role="note"`.
- **Empty state:** centered muted text + optional action, inside the card.
- Icons: inline stroke SVG (1.8 stroke, round caps), `aria-hidden="true"`; icon-only buttons get `aria-label`. No emoji, no icon fonts.

### 7.5 Screens
- **Dashboard / Patients:** header (H1 "Patients", subtitle "Read-only archive of the Allscripts EHR, practice management and pre-2010 records.");
  4 stat cards (Patients, Encounters, Lab results, Scanned documents — live counts, cached 24 h);
  search card (Search by name · Date of birth · Chart ID/MRN · Search button; wraps on narrow screens);
  patient table: Patient (link, 500) · Date of birth · Sex · Chart ID (mono) · Last visit · Records in (EMR/PM/Pre-2010 badges);
  header "All patients" + "Showing X of N · sorted by last name"; pager "Page n of m" + Previous/Next.
- **Patient chart:** "← Back to patients" link; header card (radius 12px, padding 20×22): 56px initials avatar (`--accent-soft`/`--accent-ink`),
  name 24px/600 + source badges; line 1: DOB (age) · Sex · Chart ID (mono) · PM account (mono);
  line 2: Phone · Address · Primary insurance (labels in `--muted`); right side: Print (secondary) + "Export records (PDF)" (primary with download icon).
  Tab bar: Overview · Visits · Notes · Problems & allergies · Medications · Lab results · Vitals · Documents.
  - Overview: 4 cards in `repeat(auto-fit,minmax(260px,1fr))`: Active problems (name + onset), Allergies (name + reaction in `--abn-ink`),
    Current medications (name + sig), Last visit (date 20px/600, type · provider · location, "All visits" button switching tab).
  - Visits: two columns that wrap (list `flex:1 1 380px`, detail `flex:2 1 460px`). List rows are buttons: "date · type" (500) / "provider · diagnoses" (13px muted);
    selected row `--accent-soft`. Detail: title "date · type", subline provider · location · Signed, source badge; grid of `--panel` boxes
    (Assessment, Vitals); "Visit note" section rendering the sanitised note.
  - Notes / Problems & allergies / Medications / Lab results / Vitals / Documents: tables as defined in BUILD_PROMPTS.md Phases 6–8; labs show
    abnormal flag badge; documents tab shows the warning banner while `SCAN_ROOT` is unset.

**No inline `style="…"` attributes anywhere** — the CSP in §8 blocks them. Every style is a class in `app.css`.

### 7.6 Accessibility & UX rules
Real `<button>`, `<a href>`, `<label for>`; visible focus rings; text contrast ≥ 4.5:1; touch targets ≥ 44px;
`lang="en"`; each page has a unique `<title>`; HTMX swaps target a region with `aria-live="polite"` for search results;
dates displayed `MM/DD/YYYY` (US clinic); times `h:mm AM/PM` in the clinic time zone (`CLINIC_TZ` setting).

---

## 8. Security requirements (non-negotiable)
- All routes except `/login`, `/healthz`, static files require a valid session.
- Session idle timeout 15 min, absolute timeout 8 h; rotate session id on login; delete on logout.
- Login: generic error message; lock account for 15 min after 5 failed attempts; audit every attempt.
- CSRF token on every POST. `SameSite=Lax`, `Secure` (configurable off only in local dev), `HttpOnly`.
- Headers: CSP `default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on all PHI responses.
- EMR HTML documents: sanitise with `nh3` (strip scripts, event handlers, external URLs) before rendering.
- Logs: request id, route template, status, duration, user id — **never** names, DOBs, note text, query strings with names.
- Secrets only from environment / AWS Secrets Manager; `.env` is git-ignored; `.env.example` has placeholders.

## 9. Coding conventions
- Type hints everywhere; Pydantic models for anything a template renders.
- Small functions; no business logic in templates beyond loops/conditionals.
- Each phase ends with: `ruff check . && ruff format --check . && pytest -m "not integration"` passing.
- Never invent clinical data in templates; fixtures use clearly fake names ("Sample, Patient A").
- When something in Section 4.5 is needed and unknown, add a config entry + TODO, don't guess silently.
