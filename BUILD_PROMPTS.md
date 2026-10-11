# BUILD_PROMPTS.md — Legacy Records Viewer, phase-by-phase prompts for Claude Code

## How to use
1. Create an empty repo folder `legacy-viewer/`, put **CLAUDE.md** in its root (Claude Code loads it automatically).
2. Open Claude Code in that folder. Paste **one phase prompt at a time**, in order.
3. After each phase: run the app, click through, review the diff, commit, then paste the next phase.
4. If Claude Code asks a question about unknown data (CLAUDE.md §4.5), answer it or tell it to use the config default.

Every prompt below already includes the instruction to read CLAUDE.md, stay inside the phase and stop at the end.

---

## Phase 0 — Scaffold, design system and clickable UI on fake data

```
Read CLAUDE.md fully. Implement PHASE 0 only.

Goal: a running FastAPI + Jinja2 + HTMX app that reproduces the approved design exactly (CLAUDE.md §7),
using FAKE in-memory data, so the look can be signed off before any database work.

Tasks:
1. Project setup with uv: pyproject.toml (Python 3.12) with fastapi, uvicorn[standard], jinja2, pydantic-settings,
   sqlalchemy>=2, pyodbc, psycopg[binary], alembic, argon2-cffi, nh3, weasyprint, pypdf, img2pdf, anyio, httpx,
   pytest, ruff, pyyaml. Create the full folder layout from CLAUDE.md §3 (empty modules with docstrings where not used yet).
2. app/config.py: Settings with all env vars we will need (DB host/user/password, database names, app DB URL,
   SESSION_SECRET, COOKIE_SECURE, CLINIC_NAME, CLINIC_TZ, SCAN_ROOT, FEATURE_LEGACY_DMZ, USE_FAKE_DATA=true).
   Write .env.example with placeholders only.
3. Static assets: download and vendor HTMX 2.x into app/static/vendor/htmx.min.js; vendor IBM Plex Sans (400/500/600)
   and IBM Plex Mono (400/500) woff2 into app/static/fonts with @font-face rules. No CDN references anywhere.
   Add <meta name="htmx-config" content='{"includeIndicatorStyles":false}'> so HTMX injects no inline styles.
4. app/static/css/app.css: all tokens from CLAUDE.md §7.1 and classes for every component in §7.4
   (.shell, .sidebar, .nav-link, .nav-link--active, .main, .card, .stat, .badge--emr/--pm/--legacy/--abn/--voided,
   .btn, .btn--primary, .btn--secondary, .btn--sm, .field, .input, .table-card, .table, .tabs, .tab, .tab--active,
   .banner--warn, .empty, .avatar, .panel, .visit-row, .visit-row--selected, etc.).
   NO inline style attributes anywhere (CSP forbids them) — everything is a class.
5. Templates: base.html, layout_auth.html, layout_app.html (sidebar from §7.3 with Dashboard / Patients / Release log,
   user name + Sign out), components/ macros (badge, card, stat_card, table helpers, tabs, button, input, empty_state, banner),
   pages/login.html, pages/dashboard.html, pages/chart.html, partials/patient_rows.html, partials/tab_overview.html,
   tab_visits.html, visit_detail.html, tab_notes.html, tab_problems.html, tab_meds.html, tab_labs.html, tab_vitals.html,
   tab_docs.html, pages/release_log.html, pages/errors/404.html and 500.html.
6. Fake data: tests/fakes/ with 30 obviously fake patients ("Sample, Patient A" …) and per-patient visits, notes,
   problems (problem/allergy/surgical groups), meds (incl. one "Pre-2010" source row), labs (some abnormal),
   vitals, documents. Services read from the fake repositories when USE_FAKE_DATA=true.
7. Routes from CLAUDE.md §6 wired to fake data: login page (any credentials accepted in fake mode, clearly marked
   TODO for Phase 2), /patients with HTMX search-as-you-type (hx-trigger="input changed delay:300ms") and pager,
   /patients/{key} with tab bar using hx-get + hx-push-url, ?tab= deep links rendering server-side,
   visit list → visit detail swap, documents banner when SCAN_ROOT unset.
8. Screens must match CLAUDE.md §7.5 field for field (labels, order, badges, empty states). Responsive: sidebar stacks
   on narrow screens, tables scroll horizontally inside their card, toolbars wrap.
9. /healthz returns {"status":"ok"}. Add `make dev` (or a README command) to run uvicorn with reload.
10. Tests: route smoke tests (every page and every tab returns 200 with fake data; unknown patient → 404;
    unknown tab → 404).

Done when: `uv run uvicorn app.main:app --reload` shows the three screens matching the mockup; ruff and
`pytest -m "not integration"` pass. Then stop and give me a short summary + list of files.
```

---

## Phase 1 — Source database connections (EMR, Ntier, DMZ)

```
Read CLAUDE.md. Implement PHASE 1 only.

Goal: reliable read-only connections to the three SQL Server databases and the SQL-file pattern.

Tasks:
1. app/db/source.py: one SQLAlchemy engine per database (EMR, Ntier_0010060, DMZ) built from Settings:
   mssql+pyodbc, ODBC Driver 18, Encrypt=yes, TrustServerCertificate configurable, ApplicationIntent=ReadOnly,
   pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800, login timeout 15s, query timeout 30s.
   Expose get_engine(Source.EMR | Source.NTIER | Source.DMZ). DMZ engine only created if FEATURE_LEGACY_DMZ.
2. Register a pyodbc output converter for SQL type -155 (datetimeoffset) on every new DBAPI connection via the
   SQLAlchemy "connect" event, returning timezone-aware datetime (CLAUDE.md §4.4 rule 10). Unit-test the converter
   with a packed byte sample.
3. app/db/sql_loader.py: load_sql("emr/patient_search.sql") → cached sqlalchemy text(); fail fast at startup if a
   referenced file is missing. Support expanding bind params for IN lists.
4. A base repository helper: run_query(source, sql_name, params) → list[dict], and run_scalar(...). It logs
   sql_name, row count and duration only (never params values).
5. cli.py `dbcheck`: connects to each database and prints ONLY metadata: server version, database name,
   and row counts (from sys.partitions) for EMR.HPSITE.DEMOGRAPHICS, ENCOUNTER, LAB_RESULT, SCAN_DOCUMENT,
   Ntier PM.Patients and (if enabled) DMZ conv.person. Expected: 21,384 / 2,565,968 / 1,603,126 / 626,325 / 21,330 / 9,868.
6. /readyz checks each configured source engine with SELECT 1 and the app DB (stub until Phase 2).
7. Integration tests (marked integration) that run dbcheck queries and assert the datetimeoffset converter works
   on a real row: SELECT TOP 1 TAG_SYSTEMDATE FROM HPSITE.DEMOGRAPHICS.

Do not change any UI. Done when `uv run python cli.py dbcheck` prints the counts and unit tests pass. Stop and summarise.
```

---

## Phase 2 — App database, authentication, sessions, CSRF, audit log

```
Read CLAUDE.md. Implement PHASE 2 only.

Goal: real sign-in for 5 users with one role, server-side sessions, CSRF and a complete audit trail (CLAUDE.md §5, §8).

Tasks:
1. app/db/app.py + SQLAlchemy ORM models for users, sessions, audit_log, release_log, patient_crosswalk (CLAUDE.md §5).
   Alembic set up with an initial migration. docker-compose.yml with a postgres:16 service for local dev.
2. Passwords with argon2-cffi. cli.py commands: create-user --email --name (prompts for password twice, min 12 chars),
   deactivate-user --email, reset-password --email. No sign-up page.
3. Sessions: random 32-byte token in an HttpOnly, Secure (configurable), SameSite=Lax cookie; store SHA-256 of the token;
   idle timeout 15 min (sliding), absolute 8 h; rotate on login; delete on logout. Dependency `current_user` redirects
   to /login (full page) or returns HX-Redirect header (HTMX request) when the session is missing/expired.
4. Login: generic "Email or password is incorrect"; lockout 15 min after 5 failures; update last_login_at.
   Login page keeps the Phase 0 design; add CSRF token to the form.
5. CSRF: per-session token, hidden input on every POST form and `hx-headers` for HTMX POSTs; reject mismatches with 403.
6. Audit middleware/dependency writes audit_log rows for: login, login_failed, logout, search (no search terms stored —
   store only which fields were used), view_patient, view_tab (tab name), view_document, export. Include request_id and ip.
   Writes must not block the response (background task) but must never be silently dropped (log an error on failure).
7. Security headers middleware exactly as CLAUDE.md §8 (CSP, nosniff, Referrer-Policy, Cache-Control: no-store on
   authenticated responses). Remove the fake-login TODO from Phase 0.
8. Tests: login success/failure/lockout, session expiry, CSRF rejection, audit rows written, protected routes redirect.

Done when only created users can sign in and every chart view creates an audit row. Stop and summarise.
```

---

## Phase 3 — Lookups and patient crosswalk

```
Read CLAUDE.md. Implement PHASE 3 only.

Goal: decode coded values and resolve one patient key to all source IDs.

Tasks:
1. app/lookups/: load at startup into memory:
   - sex, marital status, language, patient status from hpsystem.DICTIONARIES_MASTER / HPSITE.DICTIONARIES_SITE
     (inspect their columns first with a metadata query and write the mapping SQL in app/sql/emr/lookups_*.sql;
     if a dictionary cannot be identified, fall back to config/lookups_fallback.yaml).
   - config/history_categories.yaml (HX_DIAGNOSIS.CATEGORY_CODE → label + group problem|allergy|surgical|family|social|other).
     Seed it from HPSITE.HISTORYCATEGORY if its IDs match 18–39; otherwise ship with codes 18–39 mapped to
     "History (code N)" / group "other" and a TODO.
   - config/visit_types.yaml (ENC_VISITTYPE → label + is_office_visit), initially all "Visit type N", is_office_visit=true.
   - config/date_masks.yaml (mask value → full|month_year|year).
   API: lookups.label("sex", code) → "Unknown (code N)" when missing. Unit tests.
2. app/formatting.py: partial_date(value, mask), date_us(), datetime_local() using CLINIC_TZ, age(dob), person_name(last, first, mi),
   initials(), mask_ssn() (only last 4, if ever needed). Unit tests.
3. Crosswalk build (cli.py build-crosswalk and an admin-free startup check):
   SQL app/sql/emr/crosswalk_emr_ntier.sql:
     SELECT d.IMREDEM_CODE AS emr_id, p.Patient_ID AS ntier_id
     FROM EMR.HPSITE.DEMOGRAPHICS d
     LEFT JOIN EMR.HPSITE.EXTSYS_PATIENTINDEX x ON x.IMREDEM_CODE = d.IMREDEM_CODE
     LEFT JOIN Ntier_0010060.PM.Patients p
       ON LTRIM(RTRIM(p.Patient_Number)) COLLATE DATABASE_DEFAULT = LTRIM(RTRIM(x.PATIENTID)) COLLATE DATABASE_DEFAULT;
   Rules: one row per EMR patient in patient_crosswalk with key "EMR:<id>"; if several Ntier IDs match, keep the one
   whose Active_Patient_ID = Patient_ID (or the lowest) and set match_method "ExactId-ambiguous";
   no match → ntier_id NULL, match_method "None". Print a summary (counts per match_method) — no PHI.
   DMZ matching is NOT done here (Phase 10).
4. crosswalk.resolve(patient_key) → PatientRef(patient_key, emr_id, ntier_id, dmz_id, match_method), cached (LRU, 10 min).
   Merged-away EMR IDs (HPSITE.PATIENT_MERGE_HISTORY.ORIGINAL_DEM_CODE) resolve to the surviving CURRENT_DEM_CODE.

Done when build-crosswalk runs and prints the match summary (expect ~12,164 ExactId). Stop and summarise.
```

---

## Phase 4 — Dashboard and patient list on real data

```
Read CLAUDE.md. Implement PHASE 4 only. Keep the Phase 0 design unchanged.

Tasks:
1. Totals cards: counts from sys.partitions (fast, metadata only) for DEMOGRAPHICS, ENCOUNTER, LAB_RESULT, SCAN_DOCUMENT;
   cache 24 h.
2. app/sql/emr/patient_search.sql — page of patients, then a second query for "last visit" of only those IDs:
   SELECT d.IMREDEM_CODE AS emr_id, d.DEM_LASTNAME AS last_name, d.DEM_FIRSTNAME AS first_name,
          d.DEM_MIDDLEINITIAL AS middle_initial, d.DEM_DATEOFBIRTH AS dob, d.DEM_DATEOFBIRTHMASK AS dob_mask,
          d.DEM_SEX AS sex_code, d.DEM_CHARTID AS chart_id, d.DEM_DECEASED AS deceased,
          COUNT(*) OVER () AS total_count
   FROM HPSITE.DEMOGRAPHICS d
   WHERE NOT EXISTS (SELECT 1 FROM HPSITE.PATIENT_MERGE_HISTORY h
                     WHERE h.ORIGINAL_DEM_CODE = d.IMREDEM_CODE AND h.CURRENT_DEM_CODE <> d.IMREDEM_CODE)
     AND (:last_name IS NULL OR d.DEM_LASTNAME LIKE :last_name + '%')
     AND (:first_name IS NULL OR d.DEM_FIRSTNAME LIKE :first_name + '%')
     AND (:dob IS NULL OR d.DEM_DATEOFBIRTH = :dob)
     AND (:chart_id IS NULL OR d.DEM_CHARTID = :chart_id)
   ORDER BY d.DEM_LASTNAME, d.DEM_FIRSTNAME, d.IMREDEM_CODE
   OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY;
   app/sql/emr/last_visit_for_patients.sql: MAX(CONTACT.CON_START) per IMREDEMEC_CODE for an expanding IN list,
   excluding CON_CANCELED = 1.
   Escape % and _ in user input for LIKE. The name box accepts "Last", "Last, First" or "Last First".
3. "Records in" badges: EMR always; PM when crosswalk.ntier_id is set; Pre-2010 when dmz_id is set (only if feature on).
4. Search results swap via HTMX into the table body + pager; full-page GET with the same query params works without JS.
   Empty state: "No patients match your search." Validation errors (bad DOB format) show inline under the field.
5. Integration test: first page returns 25 rows and total_count ≈ 21,384 minus merged-away records.

Done when search and paging work against the real EMR. Stop and summarise.
```

---

## Phase 5 — Patient chart header and Overview tab

```
Read CLAUDE.md. Implement PHASE 5 only.

Tasks:
1. Header data (services/chart_header.py), queried concurrently:
   - EMR demographics: DEMOGRAPHICS (name, DOB + mask, sex, chart ID, deceased, date of death) +
     ADDRESSES via DEM_HOMEADDR (address, city, state, zip, phone) — explicit columns, no SSN.
   - EMR primary insurance: INSURANCES (lowest INS_RANK, TAG_ARCHIVED = 0) + INSURANCECARRIERS.CARRIER_NAME.
   - Ntier (if ntier_id): PM.Patients.Patient_Number, PM.Accounts.Account_Number.
   Render exactly as CLAUDE.md §7.5 (avatar initials, badges, Print + Export buttons). Missing values show "—".
2. Overview tab (services/overview.py):
   - Active problems: HX_DIAGNOSIS latest revision, group "problem" (from history_categories.yaml), not resolved, top 8 by onset desc.
   - Allergies: group "allergy" + reaction from HXDIAGNOSIS_ATTRIBUTES (TITLE/ATTRIBUTEVALUE).
   - Current medications: MEDICATIONS latest revision with no END date or END date ≥ today… plus HX_MEDICATION active ones; show name + sig.
   - Last visit: newest non-cancelled CONTACT with provider and location.
   Each card has its own empty state.
3. Audit: view_patient on chart open; view_tab for each tab load.
4. Print button: browser print with a print stylesheet (hide sidebar/tabs, show header + current tab).

Done when a real patient's header and overview render correctly. Stop and summarise.
```

---

## Phase 6 — Visits and Notes tabs

```
Read CLAUDE.md. Implement PHASE 6 only.

Tasks:
1. Visit list SQL (emr/visits_by_patient.sql): ENCOUNTER e JOIN CONTACT c ON c.IMREENC_CODE = e.IMREENC_CODE
   WHERE e.IMREDEMEC_CODE = :emr_id AND ISNULL(c.CON_CANCELED,0) = 0, columns: contact id, encounter id, CON_START,
   ENC_VISITTYPE, ENC_SIGNED, ENC_DIAGNOSES, provider (PROVIDERS via COALESCE(c.IMREPROV_CODE, e.IMREPROV_CODE)),
   LOCATION_NAME; newest first; paginated 25; filter "Office visits" (visit_types.yaml is_office_visit) / "All entries".
2. Visit detail (partial): assessment = ENCOUNTER_ASSESSMENT → DX (latest DX revision via DX_REVISION/TAG_REVISION) titles + codes;
   plan = ENCOUNTER_PLAN rows (source + sort order); vitals from VITALS_DATA for that IMREENC_CODE;
   addenda from CHART_ADDENDUM; note: (a) HTML documents linked through HTML_DOCUMENTMAP where SOURCE/SOURCE_CODE
   point to this encounter/contact → decode DOCUMENT varbinary (detect HTML vs RTF vs other by bytes), sanitise HTML with nh3,
   render inside the note section; (b) else NOTES_MASTER (IMRECONTACT_CODE) → NOTES_TEXTDATA latest revision NOTE_TEXT as
   pre-wrapped text; (c) else empty state "Visit note not available in the archive". Never render unsanitised HTML.
3. Notes tab: table Date · Note · Author · Source combining HTML_DOCUMENT_ORIG (by PATIENT_ID: CREATED_DATE, TITLE, AUTHOR),
   TRANSCRIPTION (not erroneous) and visit notes; clicking a note opens it in the same detail panel pattern.
4. Selected visit highlight, keyboard accessible; URL keeps ?tab=visits&visit=<id>.

Done when visits list, detail and notes render for real patients. Report which note source (a/b/c) was found
for 10 sample visits (counts only, no content). Stop and summarise.
```

---

## Phase 7 — Problems & allergies, Medications, Lab results, Vitals

```
Read CLAUDE.md. Implement PHASE 7 only.

Tables exactly as CLAUDE.md §7.5; each paginated (25) where lists can be long; "Show voided" toggle where relevant.

1. Problems & allergies: HX_DIAGNOSIS latest revision grouped by history_categories.yaml group
   (Problems, Allergies, Surgical history, Family history, Social history, Other) — one table/card per group:
   Title · Code (SOURCE + SOURCE_CODE) · Onset (partial date) · Resolved · Status (ACTIVITY_CODE decoded).
2. Medications: MEDICATIONS latest revision (Medication = MED_TITLE · Instructions = dose/route/frequency (or MED_INTAKE) ·
   Start · End (partial dates) · Status (MED_STATUS decoded) · Source "EMR") plus HX_MEDICATION latest revision
   (Source "EMR history"); filter Active / All; de-duplicate same title + start date.
3. Lab results: LAB_RESULT by IMREDEM_CODE: Date (RESULT_OBSERVATIONDATE) · Test (RESULT_NAME) · Result (value + units, mono) ·
   Reference range · Flag (abnormal badge when RESULT_ABNORMAL indicates abnormal or RESULT_FLAGS in H/L/HH/LL/A — mapping in config);
   filters: date range and test name; view toggle "List" / "Trend" (Trend = one test across dates, pick from a select).
4. Vitals: VITALS_DATA (exclude VITAL_ERRONEOUS_IND=1): Date · BP (systolic/diastolic) · Pulse · Temp (+unit code) ·
   Weight (+unit) · Height · SpO2 · Pain.
5. Unit tests on services with fakes; integration test per tab for one real patient (assert 200 and row counts > 0 only).

Stop and summarise.
```

---

## Phase 8 — Documents tab

```
Read CLAUDE.md. Implement PHASE 8 only.

1. Document list: SCAN_DOCUMENT by IMREDEM_CODE (DOCUMENT_DT, TITLE, SCAN_DOCUMENTTYPE.DESCRIPTION, page count from
   SCAN_DOCUMENTPAGE) + HTML_DOCUMENT_ORIG (CREATED_DATE, TITLE, AUTHOR). Columns: Date · Type · Title · Pages · Source · View.
   Filter by type; newest first; paginated.
2. app/documents/: interface DocumentStore.open(ref) → (content_type, iterator). Implementations:
   - SqlBlobStore: HTML_DOCUMENT_ORIG.DOCUMENT (sanitised HTML page) and WEBMESSAGE.ATTACHMENT.
   - FileShareStore: maps SCAN_DOCUMENTPAGE.FILELOCATION by replacing the configured UNC prefix (\\amhs-db1\hmscan)
     with SCAN_ROOT (local mount path); path traversal protection (resolved path must stay under SCAN_ROOT).
   - S3Store stub behind the same interface (not wired unless SCAN_STORE=s3).
3. Viewer page/partial: multi-page scanned documents show page images with Previous/Next; TIFF converted to PNG on the fly
   (Pillow) with a small in-memory cache; HTML documents shown sanitised. When SCAN_ROOT is unset or the file is missing,
   show the warning banner and keep metadata visible.
4. Audit view_document for every open. Streaming responses with Cache-Control: no-store.

Stop and summarise.
```

---

## Phase 9 — PDF export and release log

```
Read CLAUDE.md. Implement PHASE 9 only.

1. Export dialog (HTMX partial from the header button): checkboxes for sections (Demographics & insurance, Visits with notes,
   Problems & allergies, Medications, Lab results, Vitals, Documents), date range (from/to, optional), recipient (free text, required),
   purpose (select: Patient request, Provider request, Legal, Insurance, Other). CSRF protected POST.
2. templates/pdf/export.html + pdf.css: Letter size, 0.75in margins, IBM Plex fonts embedded; cover page
   (clinic name, "Medical records release", patient name, DOB, chart ID, date range, sections, released by, release date/time);
   every page footer: patient name · DOB · chart ID · "Page X of Y" · release id; section headings; tables reuse the same
   service view models as the screens; each record shows its source. Scanned documents appended page by page (img2pdf/pypdf)
   when available, otherwise a listing with "image not available".
3. Generate with WeasyPrint in a worker thread; stream the PDF as attachment
   (filename: release_<chartid>_<yyyymmdd>.pdf — no patient name in filename).
4. Write release_log (sections, range, recipient, page_count, sha256) and audit_log "export".
5. Release log page (sidebar): table Date · Patient (link) · Sections · Recipient · Pages · Released by; paginated; filter by date.

Stop and summarise.
```

---

## Phase 10 — Pre-2010 legacy data (DMZ), behind FEATURE_LEGACY_DMZ

```
Read CLAUDE.md. Implement PHASE 10 only. Everything here must be invisible when FEATURE_LEGACY_DMZ=false.

1. DMZ matching added to build-crosswalk:
   a) pat_extkey: if DMZ PatientMedications/cac_chrt_header pat_extkey equals an EMR IMREDEM_CODE AND conv.person.birthdate = DEMOGRAPHICS.DEM_DATEOFBIRTH
      → match_method "ExtKey".
   b) else exact normalised last name + first name + DOB → "NameDob" (confidence 0.9).
   c) unmatched DMZ persons get their own key "DMZ:<personkey>" and appear in search with only the Pre-2010 badge.
   Print counts per method. Name+DOB matches show a small "Matched by name and date of birth" note in the chart header.
2. Repositories dmz/: person demographics, chart notes (cac_chrt_header + cac_chrt_rtf → convert RTF to plain text/HTML safely),
   medications (PatientMedications + MedispanDrugs/UserDrugs for names, MedicationStatus), problems (cac_pat_prob),
   allergies (cac_pat_alrg), results (cac_results). Inspect column lists with metadata queries first; write SQL files;
   explicit columns; never select ssno.
3. Merge into existing tabs with source "Pre-2010": visits list (chart notes as visits), notes, meds, problems/allergies, labs.
   Dedupe rule: drop a DMZ row when an EMR row has the same patient, same normalised title/test and same date.
4. Tests with fakes for merge + dedupe.

Stop and summarise, including the match counts.
```

---

## Phase 11 — Hardening, packaging and deployment

```
Read CLAUDE.md. Implement PHASE 11 only.

1. Dockerfile (python:3.12-slim): install Microsoft ODBC Driver 18 (msodbcsql18) and WeasyPrint system libs (pango, cairo,
   gdk-pixbuf, fonts), non-root user, gunicorn -k uvicorn.workers.UvicornWorker -w 4, healthcheck on /healthz.
   docker-compose.yml for local (app + postgres). Run alembic upgrade on start.
2. Error handling: friendly 404/500 pages and HTMX error partials; global exception handler logs request_id only.
3. Performance: confirm every patient-scoped query uses the patient filter; add per-request timing logs; cache lookups,
   totals and crosswalk; check chart open < 1.5 s and each tab < 1 s on real data, report timings.
4. Security review against CLAUDE.md §8 (write a checklist in docs/SECURITY.md with pass/fail per item).
5. README.md: setup, env vars, create first user, build crosswalk, run, deploy (AWS: run in the same VPC as SQL Server,
   restrict 1433 to the app's security group, secrets in Secrets Manager, HTTPS via ALB/ACM).
6. Final full test run + ruff. Summarise what is complete, known gaps (CLAUDE.md §4.5 items still on defaults), and next steps.
```
