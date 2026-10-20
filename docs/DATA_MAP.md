# Data map: what each database holds and what the viewer can show

**Source:** SQL Server catalog metadata only (`sys.tables`, `sys.columns`, `sys.partitions`,
`INFORMATION_SCHEMA`), read on 2026-10-12 through the app's read-only guard. **No patient rows were read
for this document.** Row counts are catalog estimates. Code meanings marked *confirmed* come from the
archive's own lookup tables or from clinic staff.

Legend for the **Show?** column:

| Mark | Meaning |
|---|---|
| **Yes (Pn)** | Shown in the viewer; built in phase *n* of `BUILD_PROMPTS.md` |
| **Yes (live)** | Already connected to real data |
| **Maybe** | Part of the clinical record, not in the current plan. Decide before adding |
| **Lookup** | Used only to turn codes into labels; never shown on its own |
| **No** | System, configuration, logs, billing internals or integration staging. Not part of the chart |
| **NEVER** | Contains secrets or identifiers that must never be selected (see §5) |

---

## 1. The three databases at a glance

| Database | What it is | Tables (with data) | Patients | Years |
|---|---|---|---|---|
| **EMR** | Allscripts Professional EHR: the clinical chart (schema `HPSITE`, plus `hpsystem` reference data) | 1,001 (670) | 21,384 | ~2010–2023 |
| **Ntier_0010060** | Allscripts practice management: registration, insurance, appointments, billing (schema `PM`) | 494 (237) | 21,330 | — |
| **DMZ** | Pre-2010 legacy chart, staged for migration (schemas `conv`, `Medications`, `Orders`, …) | 250 (144) | 9,868 | 2002–2010 |

All three databases are on one SQL Server instance. The viewer reads only those three databases.
The instance holds 13 more databases; §9 describes them (one, **EMRTRAIN**, is an older copy of real
patient data).

---

## 2. How a patient is identified and linked

| Concept | Where | Notes |
|---|---|---|
| EMR patient key | `HPSITE.DEMOGRAPHICS.IMREDEM_CODE` | Same value appears as `IMREDEM_CODE`, `IMREDEMEC_CODE` or `PATIENT_ID` in child tables |
| **MRN** (shown as "Chart ID") | `HPSITE.PATIENT_IDENTIFIER.IDENTIFIER_VALUE` | Two types (`PATIENT_IDENTIFIER_SOURCES`): 2 = "PM 1", 3 = "Allscripts Professional PM". `DEM_CHARTID` and PM `Medical_Record_No` are empty |
| EMR ↔ PM link | `HPSITE.EXTSYS_PATIENTINDEX.PATIENTID` = `PM.Patients.Patient_Number` | 12,163 EMR patients link (12,140 exact + 23 ambiguous); 9,220 have no PM record |
| PM patient key | `PM.Patients.Patient_ID` | Name and DOB live in `PM.Contacts`, not `PM.Patients` |
| Merged EMR patients | `HPSITE.PATIENT_MERGE_HISTORY` (289 rows) | One merged-away record in the current data; the viewer redirects it |
| Legacy (DMZ) patient key | `conv.person.personkey` (= `patkey` in child tables) | No confirmed link to EMR yet. Candidates: `pat_extkey` / `conv.pat_ext_info.ext_id`, then name + DOB |
| Visit hierarchy (EMR) | Patient → `ENCOUNTER.IMREENC_CODE` → `CONTACT.IMRECONTACT_CODE` → clinical items | Visit date = `CONTACT.CON_START` |

---

## 3. EMR (`EMR`): the current clinical chart

### 3.1 Patient and demographics

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Name, DOB, sex, deceased, home address link | `DEMOGRAPHICS` (21,384) | `DEM_LASTNAME`, `DEM_FIRSTNAME`, `DEM_DATEOFBIRTH`, `DEM_SEX` (1 Male, 2 Female *confirmed*), `DEM_DECEASED`, `DEM_DATEOFDEATH`, `DEM_HOMEADDR` | **Yes (live)** |
| Address and phone | `ADDRESSES` (302,989) | `ADDR_ADDRESS`, `ADDR_CITY`, `ADDR_STATE`, `ADDR_ZIP`, `ADDR_PHONE`, `ADDR_EMAILADDRESS` | **Yes (live)**: 20,889 patients have a street, 17,562 a phone |
| MRN | `PATIENT_IDENTIFIER` (27,143), `PATIENT_IDENTIFIER_SOURCES` (2) | see §2 | **Yes (live)** |
| Race / ethnicity | `PATIENT_RACE` (21,008), `PATIENT_ETHNICITY` (21,384) | `RACE_CODE` (RACE-SUMMARY), `ETHNICITY_CODE` (ETHNICITY-SUM) | **Yes (live)**: Overview + PDF |
| Emergency contacts / health-care proxy | `PATIENT_CONTACTS` (4,642) | name, relationship (text), `PATCON_EMERGENCY`, `PATCON_HEALTHCAREPROXY` (never 1 in the data), address / phones | **Yes (live)**: Overview + PDF |
| Guarantor | `DEMGUARANTOR` (21,921) | name, DOB, address, relationship (`DEM_PATREL_TOGUARANTOR`, PATRELATION). **`GUARANTOR_SSNUM` NEVER** | **Yes (live)**: Overview + PDF |
| Care team | `PATIENT_PHYSICIANS` (46,493) | `PROVIDER_ID` → PROVIDERS, `PHYSICIAN_ROLE_CODE` (PHYSICIANROLE), `ADDED_DATE` | **Yes (live)**: Overview + PDF |
| Consents | `PATIENT_CONSENT` (21,366) | `CONSENT_CODE` (CONSENT master + site), `ANSWER_CODE` (CONANS), `EXPIRATION_DATE` | **Yes (live)**: Overview + PDF |
| Patient photo | `DEMOGRAPHICPICTURE` (10,278) | JPEG | **Yes (live)**: chart header (`/patients/{key}/photo`) |
| Merge history | `PATIENT_MERGE_HISTORY` (289) and detail (29,248) | | No (used for redirects only) |

### 3.2 Insurance

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Patient's policies | `INSURANCES` (69,085) | `INS_RANK` (0 = primary), `IMRECARRIER_CODE`, `INS_GROUPNUMBER`, `INS_PLANNUMBER`, `INS_ENROLLMENTDATE`, `INS_TERMINATIONDATE`, `TAG_ARCHIVED`. **`INS_SUBSSNUM` NEVER** | **Yes (live)**: every policy on the Overview (archived behind "Show archived") and in the PDF (archived marked); `INS_PLANTYPE` = INSPLAN, `INS_PATREL_TOSUB` = PATRELATION |
| Carriers | `INSURANCECARRIERS` (807) | `CARRIER_NAME` | **Yes (live)** |
| Pharmacy benefit eligibility | `ELIGIBILITY` (29,642) | | No |

### 3.3 Visits (encounters)

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Encounter header | `ENCOUNTER` (2,565,968) | `ENC_VISITTYPE` (codes not decoded; 98 alone = 1.67M), `ENC_SIGNED`, `ENC_DIAGNOSES`, `LOCATION_ID`, `IMREPROV_CODE` | **Yes (P6)** |
| Visit date/time, cancellation | `CONTACT` (3,060,597) | `CON_START` (visit date), `CON_END`, `CON_CANCELED`, `IMREPROV_CODE` | **Yes (live: last visit; P6 list)** |
| Assessment (diagnoses per visit) | `ENCOUNTER_ASSESSMENT` (312,736) → `DX` (96,993) | `DX_TITLE`, `DX_CODE`, `DX_SOURCE`, latest `TAG_REVISION` | **Yes (P6)** |
| Plan items | `ENCOUNTER_PLAN` (598,053) | `SOURCE`, `SOURCE_ID`, `SORTORDER` | **Yes (P6)** |
| Addenda | `CHART_ADDENDUM` (9,858) | `ADDENDUM_DT`, `IMRENOTE_CODE` → notes | **Yes (P6)** |
| Structured visit data (exam/ROS selections) | `CONTACT_DATA` (1,655,734), `CONTACTCHUNKS` (1,307,969), `HX` (1,665,798), `Hpi*` tables | knowledge-base codes; needs decoding via `*_KNOWLEDGE` tables | Maybe (the rendered note already contains this) |
| Visit review status | `REVIEWENCOUNTER` (114,024) | | No |
| Providers | `PROVIDERS` (2,407) | `PROV_LASTNAME`, `PROV_FIRSTNAME`, `PROV_TITLE`, `NPI`. **`PROV_PASSWORD`, `PROV_SSNUM`, `PROV_DEAID` NEVER** | Lookup |
| Locations | `LOCATION` (8) | `LOCATION_NAME` | Lookup |

### 3.4 Notes and documents

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Visit note text | `NOTES_MASTER` (1,657,531) → `NOTES_TEXTDATA` (1,370,268) | `NOTE_TYPE`, `NOTE_TEXT`, latest `TAG_REVISION` | **Yes (P6)** |
| Rendered clinical documents (HTML, possibly RTF) | `HTML_DOCUMENT_ORIG` (479,438), linked by `HTML_DOCUMENTMAP` (2,102,125) | `TITLE`, `AUTHOR`, `CREATED_DATE`, `DOCUMENT` (varbinary; **sanitise with nh3**) | **Yes (P6 notes, P8 viewer)** |
| Dictations / transcriptions | `TRANSCRIPTION` (3,455) + `TRANSCRIPTIONDATA` (3,455) | `DICTATED_DT`, `IMREPROV_CODE`, `trans_data`; hide `MARK_ERRONEOUS_DT` rows | **Yes (P6)** |
| Chart attachments (free-text entries) | `CHARTATTACHMENT` (57,093) | `CHAT_DATE`, `CHAT_SUBJECT`, `CHAT_CONTENT` | Maybe (likely belongs in Notes) |
| Scanned documents | `SCAN_DOCUMENT` (626,325) → `SCAN_DOCUMENTPAGE` (1,943,064), `SCAN_DOCUMENTTYPE` (306) | `DOCUMENT_DT`, `TITLE`, type `DESCRIPTION`, page `FILELOCATION` (path on `\\amhs-db1\hmscan`) | **Yes (P8)**: metadata now, images once the share is mounted |
| Release-of-information requests made in Allscripts | `PHIREQUEST` (659) + `PHIREQUEST_STATUS`, `PHIREQUEST_APPROVALSTATUS`, `PHIREQUEST_REQUESTEDINFO` (PHIRQST_INFO) | request / completed dates, status, approval, requested information, requester name (address / phone / fax not read) | **Yes (live)**: Release log → "Release requests recorded in Allscripts" |

### 3.5 Problems, allergies and history

`HX_DIAGNOSIS` (260,603) holds all history items, split by `CATEGORY_CODE`. Labels *confirmed* from
`HPSITE.HISTORYCATEGORY`:

| Code | Category | Rows | Viewer group |
|---|---|---|---|
| 24 | Problem List/Past Medical | 41,406 | Problems |
| 21 | Allergy | 26,633 | Allergies (reactions: `HXDIAGNOSIS_ATTRIBUTES.TITLE`, recorded for 3,021 of 26,458) |
| 20 | Past Surgical | 25,257 | Surgical history |
| 23 | Family | 73,225 | Family history |
| 25 | Social | 87,546 | Social history |
| 29 | Other Past History | 4,837 | Other |
| 28 | Pregnancy/Birth | 1,484 | Other |
| 18, 19, 22, 39 | Health Maintenance, Diagnostic Studies, Immunization, Impairments | 215 | Other |

Key columns: `TITLE`, `SOURCE`/`SOURCE_CODE` (code system and code), `ONSET_DATE` + `ONSETDATEMASK_CODE`,
`RESOLVED_DATE`, `ACTIVITY_CODE` (1 assumed active, *to confirm*). Latest revision: partition by
`HXDIAGNOSIS_ID`, order by `TAG_REVISION`. **Show: Yes (live: Overview; P7: full tab).**

### 3.6 Medications

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Prescriptions | `MEDICATIONS` (161,965) | `MED_TITLE`, `MED_DOSE`, `MED_DOSEUNIT`, `MED_ROUTE`, `MED_FREQUENCY`, `MED_INTAKE`, `MED_STARTDATE`, `MED_ENDDATE` (+ masks), `MED_STATUS` (1/2/3/6, not decoded), `MED_REFILLS`, `MED_QUANTITY` | **Yes (live: Overview; P7 tab)** |
| Medication history (patient-reported / reconciled) | `HX_MEDICATION` (181,404) | `TITLE`, `DOSE`, `ROUTE`, `FREQUENCY`, `START_DATE`, `END_DATE`, `ACTIVITY_CODE` | **Yes (live; P7)** |
| Refills / e-prescribing messages | `REFILL` (34,054), `ERXMESSAGE` (239,576), `EMED_REFILL_REQUEST` (37,418; **`PATIENT_SSN` NEVER**) | | No |
| Pharmacy fill history from Surescripts | `RXHUB_MED_HISTORY` (203,880) via `RXHUB_REQUEST.PATIENT_ID` (6,529 patients) | drug, strength, qty, days supply, sig, written / last fill date, prescriber, pharmacy, refills | **Yes (live)**: Medications → Pharmacy fills; PDF Medications section |

### 3.7 Labs, procedures and vitals

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Lab results | `LAB_RESULT` (1,603,126) | `RESULT_NAME`, `RESULT_VALUE`, `RESULT_UNITS`, `RESULT_NORMAL_RANGE`, `RESULT_ABNORMAL`, `RESULT_FLAGS`, `RESULT_OBSERVATIONDATE`, `RESULT_COMMENTS`, `CORRECTED` | **Yes (P7)** |
| Lab orders | `LABORDERS` (476,730), `LABSAMPLES` (467,913), `LABREQUISITION` (47,904) | `LABORDER_NAME`, `LABORDER_ORDERDATE`, `LABORDER_COMPLETIONSTATUS` (ORDCOMP: 1/2/5 open 18,408, 6 canceled 8,806, 3/4 resulted), ordering provider, diagnosis (`IMREDX_CODE` → DX), comment. Orders do not link to LAB_RESULT rows (sample codes match 249 of 477k) | **Yes (live)**: Lab results → Orders (Not resulted / Canceled / All); PDF lists open + canceled |
| Lab test catalog | `LABCATALOG` (1,873), `hpsystem.LOINC` (93,658) | | Lookup |
| Procedures / non-lab orders (imaging, referrals, in-house tests) | `PROCEDURES` (89,396) | `PROC_TITLE`, `PROC_CODE`, `PROC_ORDERDATE`, `PROC_COMPLETIONDATE`, `ABNORMAL`, `PROC_COMMENT` | Maybe (not in the current tab list) |
| Vitals | `VITALS_DATA` (138,170) | `VITAL_DATETIME`, BP, pulse, temperature (+unit), weight, height, `VITAL_PULSE_OX`, `VITAL_PAIN_LEVEL`, respiration, BMI inputs; hide `VITAL_ERRONEOUS_IND = 1` | **Yes (P6 visit detail, P7 tab)** |
| Growth percentiles | `VITALS_PERCENTILES` (138,170) | | Maybe |
| Immunizations | `IMMUNIZATIONS` (265) is the vaccine **catalog**; `IMMUNIZATION_RECORD` has 1 row; history category 22 has 14 rows | | Effectively not recorded in EMR |

### 3.8 Messages, reminders and appointments

| Information | Tables (rows) | Show? |
|---|---|---|
| Phone/internal messages about a patient | `MESSAGE` (5,441), `MESSAGE_SAVED` (128,189) | Maybe (often part of a legal record set) |
| Patient-portal messages | `WEBMESSAGE` (3,234), `WEBMESSAGE_SAVED` (2,206); `ATTACHMENT` blobs | Maybe |
| Clinical reminders | `REMINDERS` (17,650): subject, due date, priority (MSGPRIOR), completed by / on; `REM_ERRONEOUS` hidden | **Yes (live)**: Overview card + PDF |
| Appointments (EMR side) | `ARCH_SCHEDULE` (218,843): the EMR appointment table despite the `ARCH_` prefix | Maybe (PM appointments are richer, see §4) |

### 3.9 Reference data (lookups)

`hpsystem.DICTIONARIES_MASTER` (5,619) and `HPSITE.DICTIONARIES_SITE` (192) hold code → description
lists (`DICT_TYPE`, `DICT_CODE`, `DICT_DESCRIPTION`). They are the likely key to decoding `ENC_VISITTYPE`,
`MED_STATUS`, `ACTIVITY_CODE`, race/ethnicity and more. Others: `hpsystem.ICD9`, `SNOMED_MASTER`, `LOINC`,
`CVX_CODESET`, `STATES`, `COUNTRIES`, `HISTORYCATEGORY`, `SCAN_DOCUMENTTYPE`. **Lookup only.**

### 3.10 Not part of the chart (No)

| Area | Tables |
|---|---|
| Change history (old versions of rows) | All `HPSITE.ARCH_*` except `ARCH_SCHEDULE`; `HPSITE_ARCH.*`; `*_BKUP`, `*_backup` |
| Allscripts audit and error logs | `AUDIT_LOG_ORIG` (561k), `HPSITE_ARCH.AUDIT_LOG_ARCH` (23.2M), `UAIAudit` (1.2M), `ACTIVITYLOG`, `ERRORLOG`, `JOB` |
| Clinical decision support engine | `CDS.*` (incl. 93.2M-row history), `HPSITE.CDS_*` |
| Templates and knowledge bases | `Hpi*`, `*_KNOWLEDGE`, `OM_*`, `TEMPLATES`, `FLOWSHEET_*`, `QNS_*`, `RESULT_*` rule tables, `SHORTLISTS*` |
| Reports and quality measures | `RPT_*`, `RPTBO_*`, `CQM_*`, `PQRS_*`, `CATALOG_*`, `HM_*` |
| Integration engine staging | `dbo.IB_*` (contains patient/provider **SSNs**, FTP passwords), `ePHI_*`, `EXTSYS_*` (except the patient index link), `Cobra*`, `FUSION*`, `dbo.Jardogs*` |
| Portal accounts | `WPA_*`, `PORTAL_*` (contain passwords / SSNs) |
| Users, security, site configuration | `Users`, `CAREGIVER_*`, `FUNCTIONACCESS`, `SITES`, `UAI*`, `FAX*` |

---

## 4. Ntier_0010060 (`PM`): practice management

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Patient registration record | `Patients` (21,330) | `Patient_Number` (EMR link), `Account_ID`, `Contact_ID`, `Date_Registered`, `Date_First_Service`, `Date_Last_Service`, `Active_Patient_ID` | **Yes (live: link + PM badge)** |
| Account | `Accounts` (21,329) | `Account_Number` | **Yes (live: header "PM account")** |
| Person details (patients, guarantors, subscribers) | `Contacts` (31,024) | name, DOB, sex, phones, email, `Address_ID`. **`SSN`, `Drivers_License_No` NEVER** | Maybe (cross-check of demographics) |
| Addresses | `Addresses` (27,348) | street, city, state, zip, phone | Maybe |
| Insurance policies | `Patient_Policies` (24,276) → `Policies` (24,462) → `Insurance_Plans` (4,306), `Carriers` (349) | coverage order (P / S / T; X and V = inactive), group no., certificate no., effective/expiration dates, plan description, copay, policy holder. **`Carriers.Elig_Password` NEVER** | **Yes (live)**: Overview + PDF insurance table (source PM) |
| Appointments | `Appointments` (153,408), `Appointment_Types` (46), `Cancellation_Reasons` | `Appointment_DateTime`, `Duration`, `Status`, type, check-in/out, cancellation, no-show | Maybe: a good candidate for an "Appointments" tab |
| Referrals received | `Incoming_Referrals` (4,805) + `Incoming_Referral_Diags` → `Diagnosis_Codes` | dates, status (A / C / N, labels TODO confirm), authorization / pre-cert no., visits authorized, referred from / to (`Practitioners`, never SSN / Federal ID), insurance, notes | **Yes (live)**: Overview table + PDF |
| Account notes | `Notes` (20,807) | `Subject`, `Text`, `Date_Entered` (mostly billing/admin) | Maybe (admin, not clinical) |
| Custom patient fields | `Patient_Info` (46,603) + `Patient_Info_Fields` (8) | | Maybe (need field names first) |
| Billing: charges, diagnoses billed, payments, statements, remittances | `Vouchers` (89,292), `Services` (215,079), `Service_Diagnoses` (353,511), `Payments` (242,755), `Statement_History` (89,905), `ERA_*` | | No (financial records, outside the clinical release scope unless requested) |
| Providers, practitioners | `Practitioners` (1,538: **`SSN` NEVER**), `Provider_Info`, `Referring_Doctor_Info` | name, specialty | Lookup |
| Codes and setup | `Diagnosis_Codes`, `Procedure_Codes`, `Locations`, `Departments`, … | | Lookup |
| PM audit / changes | `Audit_Log` (1.7M), `Audit_Log_Detail` (5.7M), `Audit_PHI` (3.1M), `Patient_Changes` (**SSNs**), `dbo.UAIAudit` | | No / **NEVER** for `Patient_Changes` SSNs |
| Interface engine | `HIE_PM.IB_*` (FTP passwords) | | No |

---

## 5. DMZ: pre-2010 legacy chart (behind `FEATURE_LEGACY_DMZ`, off)

Full details of the separate **Pre-2010 records** section: what it shows, where each value comes from, the
assumptions, and what is not shown yet: [PRE2010_RECORDS.md](PRE2010_RECORDS.md).

| Information | Tables (rows) | Useful columns | Show? |
|---|---|---|---|
| Patients | `conv.person` (9,868) | `lname`, `fname`, `mi`, `birthdate`, `sex`, address, phones, `deceased`, `patid`. **`ssno` NEVER** | **Yes (live)** |
| Legacy chart number / external IDs | `conv.patgroup` (23,874: `chart_no`, first/last visit), `conv.pat_ext_info` (25,335: `ext_id`, `alt_id`) | | Lookup: the best candidates for linking to EMR |
| Chart notes (visits) | `conv.cac_chrt_header` (264,990) + `conv.cac_chrt_rtf` (242,438) | `service_datetime`, `drno`, `esig_status`; `note_text` (RTF → convert safely) | **Yes (live)** |
| Structured note content | `Encounters.TemplateData` (1,953,232), `Encounters.ChartGlossaries` (1,296,089) | | Maybe |
| Problems | `conv.cac_pat_prob` (32,018) | `dxcode`, `onset_date`, `stop_date`, `active_flag`, `comment`; respect `confidential` | **Yes (live)** |
| Allergies | `conv.cac_pat_alrg` (10,408) + `cac_alrg_code` (894), `Allergy.*Mapping` | allergen, symptoms, severity, status; skip `entered_error_by` rows | **Yes (live)** |
| Medications | `Medications.PatientMedications` (201,155) + `MedispanDrugs` (72,460), `UserDrugs` (918), `MedicationStatus` | `date_of_service`, `stop_date`, sig, refills, status | **Yes (live)** |
| Lab results | `conv.cac_results` (364,065) → `Orders.LabTests` → `Orders.LabOrders.patkey` (all rows reach a patient) | `labresname`, `resultvalue`, `uom`, `reflow`/`refhigh`, `abnormalflags`, `status` | Not yet: next to build (PRE2010_RECORDS §7) |
| Lab orders | `Orders.LabOrders` (24,232), `Orders.LabTests` (95,366) | | Not yet: with lab results |
| Clinical measurements (flowsheet) | `conv.cac_patclin_item` (589,381) + `cac_clin_refitem` (229) | value, `service_datetime`; skip `error_flag` | **Yes (live)**: Vitals tab + Lab results tab |
| Scanned images | `dbo.ScannedImages` (171,253), `conv.cai_images` (172,051) + `cai_imageinxs` | date, description, page count, file path on a network share | **Yes (live)**: listed; pages need `LEGACY_SCAN_ROOT` |
| Patient account notes | `conv.patnotes` (8,548) | | Maybe (admin) |
| Providers / facilities | `conv.drmast` (845: **`ssno`, `dea_num` NEVER**), `conv.facmast` | | Lookup |
| Migration bookkeeping | `conv.MigrationLog`, `*WorkTable`, `dbo.sysssislog`, `processed` columns | | No |

---

## 6. NEVER select (secrets and high-risk identifiers)

Found by scanning every column name in all three databases. The read-only guard does not know about
these: **SQL files must use explicit column lists that leave them out** (CLAUDE.md §4.4 rule 2).

| Database | Table | Columns |
|---|---|---|
| EMR | `DEMOGRAPHICS`, `ARCH_DEMOGRAPHICS` | `DEM_SSNUM` |
| EMR | `DEMGUARANTOR` | `GUARANTOR_SSNUM` |
| EMR | `INSURANCES`, `ARCH_INSURANCES` | `INS_SUBSSNUM` |
| EMR | `EXTSYS_PATIENTINDEX` (+ ARCH) | `SSN`, `DRIVERLICENSENUMBER`, `DRIVERLICENSESTATE` |
| EMR | `EMED_REFILL_REQUEST` | `PATIENT_SSN` |
| EMR | `PROVIDERS` (+ ARCH) | `PROV_PASSWORD`, `PROV_SSNUM`, `PROV_DEAID`, `PROV_LASTPASSWORDCHANGE` |
| EMR | `SITES` (+ ARCH) | `SITE_CONNECTSTRING`, `SITE_LICENSEKEY`, `SITE_SAVEEREFILLPASSWORD` |
| EMR | `Users`, `UAI_Service_Authorization`, `WPA_ACCOUNTS*`, `COMMUNITY_CONFIG` | passwords / hashes |
| EMR | `PORTAL_WEB_ACCOUNTS_PENDING*` (+ ARCH) | `WEBACCT_SSNUM` |
| EMR | `CobraTokens`, `JOB`, `UAIAudit`, `UAIDataDates`, `UAITokenSettings`, `UAILaunchMenu` | tokens |
| EMR | `dbo.IB_Patient_Info`, `IB_Appointment_Info`, `IB_Observation_Info*`, `IB_Provider_Info`, `IB_Formats*` | patient/provider SSNs, DEA, FTP passwords |
| Ntier | `PM.Contacts` | `SSN`, `Drivers_License_No` |
| Ntier | `PM.Practitioners` | `SSN` |
| Ntier | `PM.Patient_Changes` | `Patient_SSN`, `Guarantor_SSN`, `Ins1..4_Subscriber_SSN` |
| Ntier | `PM.Carriers` | `Elig_Password`, `Elig_Output_User_Password` |
| Ntier | `PM.Electronic_Claim_Formats` | `Submitter_Password` |
| Ntier | `HIE_PM.IB_Formats*` | `FTP_Password` |
| DMZ | `conv.person` | `ssno` |
| DMZ | `conv.drmast` | `ssno`, `dea_num` |
| any | database `AIE_Master` | everything |

---

## 7. Safety rules used when reading the archive

1. Every source engine refuses anything except a single `SELECT` (`app/db/readonly.py`); every `.sql` file
   is checked when loaded.
2. Explicit column lists only; never the §6 columns; latest revision only for revisioned tables.
3. Schema exploration uses catalog views only. Data checks print counts, never values.
4. Patient-scoped queries always filter on the patient key and are paged (25 rows).
5. Nothing from the source databases is written anywhere except our own app database (IDs in the
   crosswalk, audit rows without PHI).
6. The SQL login currently in use has write permissions (sysadmin). Replacing it with a `db_datareader`-only login is still
   recommended.

---

## 8. Open questions (decide or look up before building)

| Question | How to answer it (safely) |
|---|---|
| Visit type codes (`ENC_VISITTYPE`; 98 = 1.67M rows) | Look up `DICTIONARIES_MASTER` / `DICTIONARIES_SITE` descriptions (reference data, no PHI) |
| `MED_STATUS`, `ACTIVITY_CODE` meanings | Same dictionaries; or clinic staff |
| Date mask values 0, 1, 2, 4 | Dictionaries or staff (3 = full date is confirmed) |
| Which "Maybe" areas belong in the viewer and the PDF release (appointments, messages, procedures, PM insurance detail, billing) | Clinic decision: depends on what records requests usually ask for |
| DMZ ↔ EMR patient link | Counts-only match test on `pat_extkey` / `pat_ext_info.ext_id` / `patgroup.chart_no` (Phase 10) |
| Scanned image share (`\\amhs-db1\hmscan` and the legacy DMZ share) | Infrastructure: mount or copy to S3 |
| Does EMRTRAIN hold anything that EMR does not (§9.1)? | Counts-only comparison per table and date range |
| Why does EMR have visit dates up to 2026-06 when the system was retired? | Counts per year of `CON_START` (likely future-scheduled or mistyped dates) |

---

## 9. Other databases on the instance

Checked 2026-10-12 with catalog metadata only (plus counts and min/max dates for EMRTRAIN). None of them
are needed for the viewer today.

| Database | Size | What it is | Patient data? | Use in viewer |
|---|---|---|---|---|
| **AIE_Master** | 133 MB | Allscripts integration engine | Not inspected | **NEVER**: project rule (CLAUDE.md §4.4). Interface configuration and credentials |
| **EMRTRAIN** | 26 GB | Older copy of the EHR (same `HPSITE` schema), last visit Aug 2011 | **Yes, real PHI** (see §9.1) | No (treat like EMR; see open question) |
| **CDS_EMRTRAIN** | 153 MB | Decision-support engine for EMRTRAIN | No (config only, 15 small tables) | No |
| **FORMULARY** | 208 GB | Drug formulary and copay data from payers (`FORMULARY_PRODUCT` 545M rows, `CUSTOM_COVERAGE` 169M, `FORMULARY_ALTERNATIVE` 166M, `CUSTOM_COPAY_SUMMARYLEVEL` 95M) | No | No (reference) |
| **MEDISPAN** | 3.6 GB | Medi-Span drug knowledge base: drug names, GPI, dosing, interactions, RxNorm (`MDDB`, `DIB`, `MOMD`, `CSF`, `RXNORM`) | No | Lookup only, if drug names ever need decoding |
| **IMO** | 5.8 GB | Intelligent Medical Objects terminology: problem/procedure terms mapped to ICD-9/SNOMED | No | Lookup only (term → code) |
| **ATP** | 57 GB | Allscripts terminology/model service (`SvrRTModelTermRelation` 23M rows) | No | No |
| **HPI2010_SDC102** | 290 MB | Upgrade/migration work area for HPI note templates | No | No |
| **InstallationManager** | 78 MB | Allscripts installer settings | No | No |
| **MDRX_CHAT** | 130 MB | Internal chat configuration (4 user profiles) | No | No |
| **PRO_ADMIN** | 930 MB | Server monitoring ("Pinger") and configuration, incl. `CONFIG.CRYPTO*` | No | No (**NEVER** the `CRYPTO` tables) |
| **Psrx** | 34 MB | Server monitoring tasks and exception log | No | No |
| master | 6 MB | SQL Server system database | — | Not inspected |

### 9.1 EMRTRAIN: an older copy of real data

Despite the name it is **not** a training database with fake patients:

| Check (counts only) | Result |
|---|---|
| Patients in `HPSITE.DEMOGRAPHICS` | 9,836 |
| …whose ID also exists in EMR | 9,780 |
| …with the same ID, last name and DOB as in EMR | 9,254 |
| Visit dates (`CONTACT.CON_START`) | 1980-01-01 → 2011-08-13 |
| Scanned document dates | 1944-07-21 → 2019-04-08 |

It looks like a snapshot of production from around August 2011, before an upgrade. Largest tables:
`NOTES_MASTER` 499,934, `NOTES_TEXTDATA` 470,643, `CONTACT` 242,385, `SCAN_DOCUMENT` 170,552,
`ENCOUNTER` 146,897, and an older-format results table `HPSITE.RESULT` (367,385; EMR uses `LAB_RESULT`).
It contains the same sensitive columns as EMR (`DEM_SSNUM`, `PROV_PASSWORD`, `SITES.SITE_CONNECTSTRING`,
`Users.Password`, `HPSITE.CRYPTO`, …), and they fall under the same NEVER rule.

**Recommendation:** do not use EMRTRAIN as a source. EMR already covers the same period (visits from
1980). The one open question is whether anything from 2011 and earlier exists *only* in EMRTRAIN, e.g.
the 56 patients whose IDs are not in EMR, or the older `RESULT` table. A counts-only comparison can
answer that before anyone decides.
