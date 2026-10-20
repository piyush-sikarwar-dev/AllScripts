# Pre-2010 records: the legacy chart section

The viewer has a separate **Pre-2010 records** section. It shows the chart from the system the clinic
used before the Allscripts EHR, covering roughly 2002 to 2010. That data lives in the `DMZ` database,
which was staged there for a migration that never finished.

This document records what the section shows, where each value comes from, the assumptions made, and
what is still in the database but not shown. For the other databases see [DATA_MAP.md](DATA_MAP.md).

**How the facts here were gathered:** catalog metadata, counts and lookup-table labels only. Everything
was read through the app's read-only guard, between 2026-10-20 and 2026-10-21. No patient values or note
text were printed. Row counts are catalog estimates.

---

## 1. Rules that keep it separate

| Rule | How it is enforced |
|---|---|
| Separate from the current chart | Own sidebar entry, own URLs (`/legacy…`), own templates (`legacy_*`), own service and repository. The current patient list, charts, dashboard totals and PDF export never read DMZ. |
| No automatic linking to EMR patients | There is no confirmed ID link between DMZ and EMR (§8). A banner on the list says: confirm name and date of birth before relying on a record. |
| Off unless enabled | `FEATURE_LEGACY_DMZ=true` turns it on. Off: the sidebar link is hidden and every `/legacy` URL returns 404. |
| Read-only | Every query goes through `assert_read_only`. The source database is never written. |
| Audited | Every list, chart, tab, note, document and page view writes `audit_log` with `detail.section = "legacy"`. The detail holds no PHI (only the tab, page, note id or document id). |
| Patient guard | Note text, document metadata and page images are fetched with **both** the item id **and** the patient key. Another patient's item returns 404. |
| Never selected | `conv.person.ssno`, `conv.drmast.ssno`, `conv.drmast.dea_num`. A unit test checks that no `legacy_*.sql` file selects `ssno` or uses `SELECT *`. |

Patient key format: `DMZ:<personkey>` (validated with `DMZ:\d{1,10}`; anything else returns 404).

---

## 2. Turning it on

| Setting (`.env`) | Default | Meaning |
|---|---|---|
| `FEATURE_LEGACY_DMZ` | `false` | Shows the section. |
| `LEGACY_SCAN_ROOT` | unset | Folder holding a copy of the old image share. Unset: the Documents tab lists the documents but cannot show their pages, and a banner says so. |
| `LEGACY_SCAN_UNC_PREFIX` | `\\w10060-1\images` | The UNC prefix stored in `ScannedImages.fpath`; it is replaced by `LEGACY_SCAN_ROOT`. Paths that resolve outside the root are refused. |

The DMZ engine itself uses the same read-only SQL login as EMR and Ntier (`DMZ_DATABASE`, default `DMZ`).

---

## 3. Screens and routes

| Route | What it shows |
|---|---|
| `GET /legacy` | Patient list: name, date of birth, sex, legacy ID. Search by name ("Last, First"), DOB or legacy ID; 25 per page; search-as-you-type. |
| `GET /legacy/rows` | HTMX fragment of the list (pushes the full-page URL). |
| `GET /legacy/{key}?tab=…` | Legacy chart: header plus tabs. Every tab URL works as a full page load. |
| `GET /legacy/{key}/tab/{name}` | HTMX fragment of one tab. |
| `GET /legacy/{key}/notes` | Notes list fragment (year filter, paging). |
| `GET /legacy/{key}/notes/{note_id}` | One chart note. |
| `GET /legacy/{key}/notes/{note_id}/print` | Printable note page (no sidebar; the print dialog opens automatically). |
| `GET /legacy/{key}/documents/{doc_id}` | Document viewer fragment. |
| `GET /legacy/{key}/documents/{doc_id}/pages/{n}` | One scanned page as PNG. Only works when `LEGACY_SCAN_ROOT` is set. |

**Header:** name (with suffix), *Pre-2010* badge, *Deceased* badge, DOB and age, sex, legacy ID
(`patid`), home phone, address.

**Tabs:** Overview · Chart notes · Problems & allergies · Medications · Lab results · Vitals · Documents.

---

## 4. Where each tab's data comes from

Rows in brackets are catalog estimates for the whole database.

### 4.1 Patients and header
- `conv.person` (9,868): `lname`, `fname`, `mi`, `suffix`, `birthdate`, `sex` (F/M/U), `deceased`,
  `street1/2`, `city`, `state`, `zip`, `harea`+`hphone`, `patid`.
- SQL: `legacy_patient_search.sql` (paged, `COUNT(*) OVER ()` for the total), `legacy_patient.sql`.
- 255 of 9,868 patients (2.6%) have no date of birth in the source; no age is shown for them.

### 4.2 Overview
Built from the other tabs: active problems with onset, active allergies with reactions, medications
active at the last pre-2010 update with sig, and the last chart note. A counts row links to each tab.
Opening the Overview loads every tab's data in parallel, so later tab switches come from the cache.

### 4.3 Chart notes
- `conv.cac_chrt_header` (264,990): `note_id`, `patkey`, `service_datetime`, `drno` → `conv.drmast`
  (`lname`, `fname`, `title` only), `faccode` → `conv.facmast.facname`.
- `conv.cac_chrt_rtf` (242,438): `note_text` RTF, normally one row per note (joined in `rownum`
  order), converted to plain text with `rtf_to_text`. Field results are kept; field instructions,
  headers, footers and font tables are dropped.
- 22,552 notes have no text row. **All of them are "ORDER MANAGEMENT RESULT" notes, and every one is
  linked to lab results** (`Encounters.NoteResultLink`). Their content is the lab result itself, which is
  not shown yet (§7, items 1 and 3). They are listed as "Chart note (no text)".
- Many notes contain a literal drive-letter path (`X:\..\..\…`) that the old system printed into the
  text. It is real note content and is shown as written.
- 449 notes are dated before 2002 and 252 after 2010-08-27 (data-entry outliers); they are shown as
  stored.
- The legacy system recorded no electronic signature (`esig_*` is empty in every row).

### 4.4 Problems & allergies
- Problems: `conv.cac_pat_prob` (32,018): `dxcode` → `conv.dxmast` (`dxdesc1` + `dxdesc2`; 32,017 of
  32,018 found), `onset_date`, `stop_date`, `prob_stat_key`, `comment`, `drno` → provider.
- Allergies: `conv.cac_pat_alrg` (10,408):
  - `alrg_code_key` → `conv.cac_alrg_code.name` / `description`
  - `alrg_cat_key` → `conv.cac_alrg_cat`
  - `alrg_stat_key` → `conv.cac_alrg_status`
  - `severity_key` → `conv.cac_control_values` (lookup keys 173 Severe, 174 Moderate, 175 Mild,
    176 Not available)
  - reactions: `conv.cac_pat_alrg_det` → `conv.cac_adv_reactions`
- Entered-in-error rows are hidden behind **Show entered-in-error** and get a *Voided* badge when shown.
  These are problem status 30, allergy status 30 or 999, or allergy `active_flag = 'E'`.
- No problem, allergy or result in this database is flagged `confidential`, so no extra filtering is
  needed.

### 4.5 Medications
- `Medications.PatientMedications` (201,155). One medication's entries share `parent_key`
  (new prescription, then continued, then discontinued). This gives 113,418 medications with about
  1.8 entries each.
- Drug name: `MedispanDrugs.disp_name`, else `UserDrugs.disp_name` + `strength`.
- Sig: `MedicationSigWorkTable` (`Quantity` + `DoseForm` + `Frequency`).
- Quantity: `amt_dispensed` + `conv.cac_amt_uom.abbrev`.
- Reason: `dxcode` → `conv.dxmast`.
- Status: `Medications.MedicationStatus` (`MEMR_Med_Description`). Its `PROEHR_Med_Status` gives the
  group: 1 = active, 3 = discontinued, 6 = entered in error, 2 = deleted.
- Screen: one row per medication (latest entry), with **History (N entries)** listing every entry.
  Sections are *Active at last pre-2010 update*, *Discontinued*, and *Entered in error* (behind the
  toggle).
- `PatientMedicationRemarks` (10,427) is identical to `PatientMedications.comments` in every row, so
  only `comments` is read.

### 4.6 Lab results and Vitals
- Both tabs read `conv.cac_patclin_item` (589,381) + `conv.cac_clin_refitem.name` (the
  clinical-value flowsheet). Rows with `error_flag = 'Y'` are left out (none today).
- **Vitals** are the item names listed under `vital_items` in `config/legacy_codes.yaml`: VS-BLOOD
  PRESSURE, VS-PULSE, VS-TEMPERATURE, VS-RESPIRATION, VS-WEIGHT, VS-HEIGHT, BMI, WAIST MEASUREMENT.
  They are grouped into one row per recorded time and shown as entered, with units in the value
  (for example `180lb`, `5ft10in`).
- **Lab results** are every other item: date, test, result, reference range (`reflow` / `refhigh`),
  a High/Low flag computed for plain numeric results, and comments. There are test and year filters.
- Skipped: `GENERIC-*` and `HEALTH MAINT-*` items. These are template fields (date, time and phone
  entries) that mean nothing on their own; the phone entries contain phone numbers.
- Where the value came from a chart note, **Open note** opens it.
- This flowsheet has **no units** for lab values. The full lab system with units, flags and orders
  has not been built yet (§7, item 1).

### 4.7 Documents
- `dbo.ScannedImages` (171,253): `DocDate`, `MRCName` (document type, shown as stored, e.g. HIPAA,
  OUTSIDE LABS), `ipages`, `FileExt` (TIF 168,971 / JPG 2,282), `drno`, `noteid`. Every scanned
  document is linked to a chart note.
- The file path (`fpath`) is read one document at a time, together with the patient key, and only
  when a page is requested.
- Files are on `\\w10060-1\images`, which **does not resolve from this network**. The tab lists
  every document and explains that the pages cannot be shown yet. Copying the share and setting
  `LEGACY_SCAN_ROOT` makes the pages display as PNG (each TIFF frame is a page).
- `conv.cai_images` / `conv.cai_imageinxs` (172k) describe the same images (every `Imageid` matches)
  and are not read.

---

## 5. Configuration and assumptions

`config/legacy_codes.yaml` holds the legacy codes that have no lookup table in the database:

| Key | Content | Status |
|---|---|---|
| `problem_status` | 12 Active, 11 Inactive, 30 Entered in error | **TODO: confirm with the clinic.** No lookup table exists. The mapping follows the allergy status keys. 12 holds 92% of rows and never has a stop date. |
| `problem_voided` / `allergy_voided` | `[30]` / `[30, 999]` | Hidden unless "Show entered-in-error" is on. |
| `severity_blank` | `Not Available` | Shown as "—". |
| `vital_items` | vitals column → item name | Add a name here to move an item from Labs to Vitals. |
| `skip_item_prefixes` | `GENERIC-`, `HEALTH MAINT-` | Not shown anywhere. |

Unknown codes display as `Unknown (code N)` and never raise an error.

---

## 6. Performance

- The DMZ tables have **no index on the patient column** for medications, clinical items and scanned
  images (`cac_chrt_header` and `cac_pat_alrg` do have one). We cannot add indexes, because the
  database is read-only for us.
- Measured on the real data, the per-patient queries are still fast: about 0.1–0.2 s per tab. The
  heaviest patient takes about 0.6 s on a first visit, then reads come from the per-patient cache.
  The first list page after a server start takes about 1 s (cold connection), then about 0.2 s.
- When the data moves to our own server, add indexes on `patkey` for
  `Medications.PatientMedications`, `conv.cac_patclin_item`, `dbo.ScannedImages`,
  `conv.cac_pat_prob` and `Orders.LabOrders`.

---

## 7. What is in the database but not shown yet

Ordered by usefulness to a records request.

| # | Information | Tables (rows) | What it adds | Recommendation |
|---|---|---|---|---|
| 1 | **Lab orders and results (full lab system)** | `Orders.LabOrders` (24,232, `patkey`), `Orders.LabTests` (95,366), `conv.cac_results` (364,065), `conv.cac_rescom` (61,787 result comments), `Orders.TaskQueueComments` (49,814 order/result comments), `conv.cac_diaglink` (120,846 order diagnoses), `conv.cac_specimens` (91,669) | Results with **units** (89%), reference ranges (99.8%), lab abnormal flags (H 28k, L 19k, A 281), status (final/preliminary), the ordering provider, order date, fasting, the diagnosis for each order, and result comments. The chain `cac_results.systestordered → LabTests.systestorderno → LabOrders.sysorderno → patkey` reaches a patient for **all 364,065 results** (5,231 patients). | **Build next.** Either replace the flowsheet labs or show both (orders and results as the main view, the flowsheet as "Lab values recorded in notes"). |
| 2 | **Chart note type** | `Encounters.MRC` (277) via `cac_chrt_header.mrc_key` | Every note currently says "Chart note". Real types: DEC FOLLOW-UP VISIT (33k), ORDER MANAGEMENT RESULT (22.5k), OUTSIDE LABS (22k), NURSE PHONE CALL (19k), DEC CONSULT (5.9k), letters, insurance cards, HIPAA and more. | **Small, high value.** Show the type as the note title and add a type filter. |
| 3 | Note ↔ lab result link | `Encounters.NoteResultLink` (89,968; 22,552 notes) | The 22,552 "ORDER MANAGEMENT RESULT" notes have no text: their content *is* these results. Linking them shows the results inside the note instead of "no text". | Build with #1. |
| 4 | More demographics | `conv.person`: `marstat` (7,877 filled), `race` (7,000), work phone `warea`/`wphone`/`wext` (6,015), `entrydate` | Marital status, race, work phone and the date the chart was created. `email`, `alias` and `confidential` are empty. Codes need decoding (no lookup table seen yet). | Add to the header or an "About" card; decode via config. |
| 5 | Primary provider and facility | `conv.patgroup` (23,874): `drno` (21,997 filled), `faccode` (19,759) | Who the patient's doctor was and which office. `fvisit`, `lvisit` and `chart_no` are empty. | Add to the header. |
| 6 | Patient account notes | `conv.patnotes` (8,548; 5,861 patients; type CLRT) | Front-desk account notes (`notetext`, entry date, user). Administrative, may include billing remarks. | **Ask the clinic** whether these belong in a medical-records release. |
| 7 | Patient photo | `conv.cac_pat_photo` (4,658; about 107 KB each) | A photo for identity checks. | Optional: show in the header avatar. |
| 8 | Past history (medical / surgical / family / social) | `dbo.Gloss_base` (80,602; about 5.9k patients; category codes 23, 25, 24, 20, 18) | History entries with text. The category codes match EMR `HX_DIAGNOSIS` categories, and the table carries EMR ids (`hxdiagnosis_id`, `EncounterID`). It looks like a staging table for history that was already moved into EMR. | Check a count-only overlap with EMR `HX_DIAGNOSIS` first; show it only if it is not already in EMR. |
| 9 | Preferred pharmacy | `conv.cac_pat_pharm_pref` (4,201) → `conv.cac_erx_pharm` | Patient's pharmacy. | Low priority. |
| 10 | External IDs (for linking to EMR) | `conv.pat_ext_info` (25,335; 23,323 patients): `ext_id`, `alt_id` | The best candidate for linking DMZ patients to EMR patients (counts-only match test still to do). | Use for a "Possible match in current records" hint, never an automatic merge. |
| 11 | Structured note content | `Encounters.TemplateData` (1,953,232), `Encounters.ChartGlossaries` (1,296,089) | The same content as the RTF note text, broken into template items (glossary, meds, sig, labs, assessment). | No: the RTF text already shows it. |
| 12 | Procedures, consent | `Procedures.PatientProcedures` (9 rows, 8 patients), `Patient.Consent` (11) | Almost empty. | No (or a small list if requested). |
| — | Immunizations, separate vitals table | `Immunizations.PatientImmunizations`, `Vitals.Vitals` | **Empty** (0 rows). | Nothing to show. |

**Not part of the chart (never shown):** migration bookkeeping (`conv.MigrationLog`, `*WorkTable`,
`dbo.sysssislog`, `processed` columns), staging copies of results (`dbo.TestSaveresultstbl`,
`dbo.TestResultOrdertbl`, `dbo.Resultsmigratetbl`), audit trails (`conv.cac_order_track`,
`cac_result_track`, `cac_test_track`), templates and glossary definitions (`Templates.*`,
`Glossary.*`, `Prenatal.PreNtlWork`), provider favourites (`MyLists.*`, `Providers.cac_myallergies`),
interface mappings (`conv.iface_map_*`, `Interface.*`) and lookups such as `conv.cac_ndc`.

---

## 8. Open questions

| Question | Who / how |
|---|---|
| What do problem status codes 11 / 12 / 30 mean? | Clinic staff. Change `problem_status` in `config/legacy_codes.yaml`. |
| Can a DMZ patient be matched to an EMR patient? | Counts-only match test on `pat_extkey` / `pat_ext_info.ext_id` / `alt_id`, then name + DOB. Show a hint, never merge. |
| Where can the old image share (`\\w10060-1\images`) be copied from? | Infrastructure: copy it to S3 or a mounted folder, then set `LEGACY_SCAN_ROOT`. |
| Should pre-2010 records be part of the PDF release export? | Clinic. Today they can only be printed note by note; the release export covers the current chart only. |
| Do account notes (`conv.patnotes`) belong in a records release? | Clinic. |

---

## 9. Code map

| Layer | Files |
|---|---|
| SQL (one query per file) | `app/sql/dmz/legacy_patient_search.sql`, `legacy_patient.sql`, `legacy_notes.sql`, `legacy_note_text.sql`, `legacy_problems.sql`, `legacy_allergies.sql`, `legacy_allergy_reactions.sql`, `legacy_medications.sql`, `legacy_clinical_items.sql`, `legacy_documents.sql`, `legacy_document_file.sql` |
| Repository | `app/repositories/dmz/__init__.py` (one function per SQL file); `app/repositories/legacy.py` (cached per patient, sorting, joins in Python); `legacy_repository()` in `app/repositories/__init__.py` selects the fake or the live module |
| Lookups / config | `app/lookups/legacy_codes.py`, `config/legacy_codes.yaml` |
| Service | `app/services/legacy.py` (search, header, tabs, notes, history, medications, labs, vitals, documents, overview) |
| View models | `app/models/legacy.py` |
| Router | `app/routers/legacy.py` (requires a session; 404 when the feature is off) |
| Document store | `get_legacy_store()` in `app/documents/store.py`; settings in `app/config.py` |
| Templates | `pages/legacy_list.html`, `legacy_chart.html`, `legacy_note_print.html`; `partials/legacy_rows.html`, `legacy_tab_frame.html`, `legacy_tab_{overview,notes,problems,meds,labs,vitals,docs}.html`, `legacy_notes.html`, `legacy_note.html`, `legacy_doc_viewer.html` |
| Styles | `app/static/css/app.css`, section "Pre-2010 records" |
| Tests | `tests/fakes/legacy.py` (clearly fake data), `tests/unit/test_legacy_section.py` (37 tests: search, tabs, guards, audit, feature flag, page images from a sample share copy, RTF conversion) |
