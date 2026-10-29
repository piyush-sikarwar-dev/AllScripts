# Data inventory: every source table and column the app reads

Generated on 2026-10-29 from the code, then checked against the live SQL Server catalog. **Read-only:** only
catalog metadata was queried (`INFORMATION_SCHEMA.COLUMNS`, `sys.partitions`, `sys.databases`); no row
data was read and nothing was changed.

Column-level detail: [data_inventory_columns.csv](data_inventory_columns.csv) (one row per table + column).
Table-level detail: [data_inventory_tables.csv](data_inventory_tables.csv).

**How it was built:**
1. Every SQL file under `app/sql/` (98 files) was parsed: tables (including three-part cross-database
   names), aliases, and each column's role (select / join / filter / sort), aware of nested subqueries.
   There is no other SQL in the app: the only inline statements are two `SELECT 1` connection checks.
2. Each SQL file was traced through the code: SQL file → repository function (`app/repositories/{emr,ntier,dmz}`)
   → caller (`live.py` / `legacy.py` / `cli.py` / `security.py` / `routers/health.py`) → service → screen.
3. Every table and column was checked to exist in the database (`INFORMATION_SCHEMA.COLUMNS`). Row counts
   come from `sys.partitions` (`index_id IN (0,1)`).

---

## 1. Summary

| Database | Tables used | Columns used | Rows in tables used | Tables on server | Rows on server | Notes |
|---|---|---|---|---|---|---|
| **EMR** | 55 | 376 | 19,952,115 | 1,001 | 210,936,977 |  |
| **Ntier_0010060** | 16 | 76 | 378,032 | 494 | 19,820,075 |  |
| **DMZ** | 45 | 238 | 2,700,943 | 250 | 10,304,458 | Only when `FEATURE_LEGACY_DMZ` is on |
| **Total** | **116** | **690** | **23,031,090** | 1,745 | 241,061,510 | |

The app reads **116 of 1,745 tables** in its three databases. Those tables hold **23,031,090 rows** (10% of the 241,061,510 rows in the three databases). It never scans them whole: every chart query is limited to one patient (§6).

**Checks:**
- Columns referenced in code that don't exist in the database: **0**.
- Sensitive columns selected anywhere: **0** (§5).
- SQL files no screen reaches: **1**, `emr/transcriptions.sql` (§6).

---

## 2. EMR (Allscripts EHR), schemas `HPSITE`, `HPSITE_ARCH`

| Schema.Table | Rows | Used by screen(s) | Purpose | Key columns (join / filter) | Notes |
|---|---|---|---|---|---|
| `HPSITE.ADDRESSES` | 302,989 | Overview; PDF export; Patient header; Print | data | `IMREADDR_CODE` |  |
| `HPSITE.ARCH_HXDIAGNOSIS` | 361,475 | Problems & allergies | data | `HXDIAGNOSIS_ID`, `PATIENT_ID` | Change history only (Problems & allergies → Change history); never the current state |
| `HPSITE.ARCH_SCHEDULE` | 218,843 | Appointments; PDF export | data | `IMREDEM_CODE`, `IMREPROV_CODE`, `LOCATION_ID` | The EMR appointment table (exception to the ARCH_* rule) |
| `HPSITE.CHARTATTACHMENT` | 57,093 | Documents; PDF export | data | `IMREDEMEC_CODE`, `IMRENOTE_CODE`, `IMREPROV_CODE`, `TAG_ARCHIVED` |  |
| `HPSITE.CHART_ADDENDUM` | 9,858 | PDF export; Print; Visits | data | `IMREENC_CODE`, `IMRENOTE_CODE`, `IMREPROV_CODE` |  |
| `HPSITE.CONTACT` | 3,060,597 | CLI only; Dashboard / patient list; Overview; PDF export; Print; Problems & allergies; Visits | data | `CON_CANCELED`, `IMRECONTACT_CODE`, `IMREENC_CODE`, `IMREPROV_CODE` |  |
| `HPSITE.DEMGUARANTOR` | 21,921 | Overview; PDF export | data | `GUARANTOR_ADDRESS`, `GUARANTOR_CODE` | GUARANTOR_SSNUM never read |
| `HPSITE.DEMOGRAPHICPICTURE` | 10,278 | Overview; PDF export; Patient header; Print | data | `IMREDEM_CODE` | Large: `DEM_PICTURE varbinary(max)` |
| `HPSITE.DEMOGRAPHICS` | 21,384 | CLI build-crosswalk (patient links); CLI only; Dashboard / patient list; Notes (message names); Overview; PDF export; Patient header; Print; Release log | data | `DEM_DATEOFBIRTH`, `DEM_FIRSTNAME`, `DEM_HOMEADDR`, `DEM_LASTNAME`, `GUARANTOR_CODE`, `IMREDEM_CODE` | DEM_SSNUM never read |
| `HPSITE.DX` | 96,993 | Lab results; PDF export; Visits | data | `IMREDX_CODE`, `TAG_REVISION` |  |
| `HPSITE.ENCOUNTER` | 2,565,968 | CLI only; Dashboard / patient list; Notes; Overview; PDF export; Print; Visits | data | `ENC_VISITTYPE`, `IMREDEMEC_CODE`, `IMREENC_CODE`, `IMREPROV_CODE`, `LOCATION_ID` |  |
| `HPSITE.ENCOUNTER_ASSESSMENT` | 312,736 | PDF export; Visits | data | `DX_ID`, `DX_REVISION`, `ENCOUNTER_ID` |  |
| `HPSITE.ENCOUNTER_PLAN` | 598,053 | PDF export; Print; Visits | data | `ENCOUNTER_ID`, `SOURCE`, `SOURCE_ID` |  |
| `HPSITE.EXTSYS_PATIENTINDEX` | 26,750 | CLI build-crosswalk (patient links) | join | `IMREDEM_CODE`, `PATIENTID` | EMR ↔ PM link (crosswalk build); SSN / driver-licence columns never read |
| `HPSITE.HTML_DOCUMENTMAP` | 2,102,125 | Notes; PDF export; Print; Visits | join | `DOCUMENT_ID`, `SOURCE`, `SOURCE_CODE` |  |
| `HPSITE.HTML_DOCUMENT_ORIG` | 479,438 | Documents; Notes; PDF export; Print; Visits | data | `DOCUMENT_ID`, `PATIENT_ID` | Large: `DOCUMENT varbinary(max)` |
| `HPSITE.HXDIAGNOSIS_ATTRIBUTES` | 74,971 | Overview; PDF export; Problems & allergies | data | `HXDIAGNOSIS_ID` |  |
| `HPSITE.HX_DIAGNOSIS` | 260,603 | Overview; PDF export; Problems & allergies | data | `CATEGORY_CODE`, `HXDIAGNOSIS_ID`, `PATIENT_ID` |  |
| `HPSITE.HX_MEDICATION` | 181,404 | Medications; Overview; PDF export | data | `PATIENT_ID` |  |
| `HPSITE.INSURANCECARRIERS` | 807 | Overview; PDF export; Patient header; Print | lookup | `CARRIER_ADDRCODE`, `IMRECARRIER_CODE` |  |
| `HPSITE.INSURANCES` | 69,085 | Overview; PDF export; Patient header; Print | data | `IMRECARRIER_CODE`, `IMREDEM_CODE`, `TAG_ARCHIVED` | INS_SUBSSNUM never read; archived rows behind “Show archived” |
| `HPSITE.LABCATALOG` | 1,873 | Lab results; PDF export | lookup | `IMRELABCAT_CODE` |  |
| `HPSITE.LABORDERS` | 476,730 | Lab results; PDF export; Print; Visits | data | `IMREDEMEC_CODE`, `IMREDX_CODE`, `IMRELABCAT_CODE`, `IMRELABORDER_CODE`, `IMREPROV_CODE` |  |
| `HPSITE.LAB_RESULT` | 1,603,126 | Lab results; PDF export | data | `IMREDEM_CODE` |  |
| `HPSITE.LOCATION` | 8 | Appointments; Overview; PDF export; Print; Visits | lookup | `LOCATION_ID` |  |
| `HPSITE.MEDICATIONS` | 161,965 | Medications; Overview; PDF export; Print; Visits | data | `IMREDEMEC_CODE`, `IMREMED_CODE` |  |
| `HPSITE.MESSAGE_SAVED` | 128,189 | Documents; Notes; PDF export; Print | data | `IMREDEM_CODE`, `IMREENC_CODE`, `IMREMESSAGE_CODE`, `IMRENOTE_CODE`, `MSG_FROMPROVCODE`, `MSG_TOPROVCODE` |  |
| `HPSITE.NOTES_MASTER` | 1,657,531 | PDF export; Print; Visits | join | `IMRECONTACT_CODE`, `IMRENOTE_CODE` |  |
| `HPSITE.NOTES_RAWDATA` | 54,760 | Documents; PDF export | data | `IMRENOTE_CODE` | Large: `NOTE_DATA varbinary(max)` |
| `HPSITE.NOTES_TEXTDATA` | 1,370,268 | Documents; Notes; PDF export; Print; Visits | data | `IMRENOTE_CODE` | Large: `NOTE_TEXT varchar(max)` |
| `HPSITE.PATIENT_CONSENT` | 21,366 | Overview; PDF export | data | `PATIENT_ID` |  |
| `HPSITE.PATIENT_CONTACTS` | 4,642 | Overview; PDF export | data | `IMREDEM_CODE`, `PATCON_ADDRESS` |  |
| `HPSITE.PATIENT_ETHNICITY` | 21,384 | Overview; PDF export | data | `PATIENT_ID` |  |
| `HPSITE.PATIENT_IDENTIFIER` | 27,143 | CLI only; Dashboard / patient list; PDF export; Patient header; Print | data | `IDENTIFIER_VALUE`, `PATIENT_ID` |  |
| `HPSITE.PATIENT_MERGE_HISTORY` | 289 | CLI build-crosswalk (patient links); CLI only; Dashboard / patient list | join | `CURRENT_DEM_CODE`, `ORIGINAL_DEM_CODE` | Merged patients (crosswalk build, redirects) |
| `HPSITE.PATIENT_PHYSICIANS` | 46,493 | Overview; PDF export | data | `PATIENT_ID`, `PROVIDER_ID` |  |
| `HPSITE.PATIENT_RACE` | 21,008 | Overview; PDF export | data | `PATIENT_ID` |  |
| `HPSITE.PHIREQUEST` | 659 | Release log | data | `APPROVALSTATUS`, `ENTRYPROVID`, `STATUS` |  |
| `HPSITE.PHIREQUEST_APPROVALSTATUS` | 4 | Release log | lookup | `STATUSID` |  |
| `HPSITE.PHIREQUEST_REQUESTEDINFO` | 110 | Release log | data | — |  |
| `HPSITE.PHIREQUEST_STATUS` | 3 | Release log | lookup | `STATUSID` |  |
| `HPSITE.PROCEDURES` | 89,396 | PDF export; Print; Visits | data | `IMREPROC_CODE` |  |
| `HPSITE.PROVIDERS` | 2,407 | Appointments; Documents; Lab results; Notes; Overview; PDF export; Print; Problems & allergies; Release log; Visits | lookup | `IMREPROV_CODE`, `PROV_FIRSTNAME`, `PROV_LASTNAME` | Names / title only; PROV_PASSWORD, PROV_SSNUM, PROV_DEAID never read |
| `HPSITE.REMINDERS` | 17,650 | Overview; PDF export | data | `IMREDEMEC_CODE`, `REM_COMPLETEDBYPROV`, `REM_ENTEREDBYPROV` |  |
| `HPSITE.RXHUB_MED_HISTORY` | 203,880 | Medications; PDF export | data | `RXHUB_ID` |  |
| `HPSITE.RXHUB_REQUEST` | 8,309 | Medications; PDF export | join | `PATIENT_ID`, `RXHUB_ID` |  |
| `HPSITE.SCAN_DOCUMENT` | 626,325 | Documents; PDF export | data | `DOCUMENT_ID`, `IMREDEM_CODE`, `SCAN_ID` |  |
| `HPSITE.SCAN_DOCUMENTPAGE` | 1,943,064 | Documents; PDF export | data | `DOCUMENT_ID` |  |
| `HPSITE.SCAN_DOCUMENTTYPE` | 306 | Documents; PDF export | lookup | `SCAN_ID` |  |
| `HPSITE.TRANSCRIPTION` | 3,455 | Documents; Notes; PDF export; Print | data | `IMREDEM_CODE`, `IMREENC_CODE`, `IMREPROV_CODE`, `MARK_ERRONEOUS_DT`, `TRANSCRIPTION_ID` | Also read by transcriptions.sql, which only the replaced Notes tab calls (unused) |
| `HPSITE.TRANSCRIPTIONDATA` | 3,455 | Documents; Notes; PDF export; Print | data | `TRANSCRIPTION_ID` | Large: `trans_data varchar(max)` |
| `HPSITE.VITALS_DATA` | 138,170 | PDF export; Print; Visits; Vitals | data | `IMRECONTACT_CODE`, `IMREDEM_CODE`, `IMREENC_CODE`, `VITAL_ERRONEOUS_IND` |  |
| `HPSITE.WEBMESSAGE` | 3,234 | Documents; Notes; PDF export; Print | data | `ATTACHMENT`, `IMREDEM_CODE`, `IMREPROV_CODE`, `ORIG_PROVCODE`, `WEBMSG_ID` | Large: `ATTACHMENT varbinary(max)`, `BODY_TEXT varchar(max)` |
| `HPSITE.WEBMESSAGE_SAVED` | 2,206 | Documents; Notes; PDF export; Print | data | `IMREDEM_CODE`, `IMREENC_CODE`, `IMREPROV_CODE`, `ORIG_PROVCODE`, `WEBMSG_ID` | Large: `BODY_TEXT varchar(max)` |
| `HPSITE_ARCH.HTML_DOCUMENT_ARCH` | 479,336 | Documents; Notes; PDF export; Print; Visits | data | `DOCUMENT_ID` | Large: `DOCUMENT varbinary(max)`; Archived copies of clinical documents (fallback when the original is missing) |

---

## 3. Ntier_0010060 (practice management), schema `PM`

| Schema.Table | Rows | Used by screen(s) | Purpose | Key columns (join / filter) | Notes |
|---|---|---|---|---|---|
| `PM.Accounts` | 21,329 | PDF export; Patient header; Print | data | `Account_ID` |  |
| `PM.Appointment_Types` | 46 | Appointments; PDF export | lookup | `Appointment_Type_ID` |  |
| `PM.Appointments` | 153,408 | Appointments; PDF export | data | `Appointment_Type_ID`, `Cancellation_Reason_ID`, `Is_Memo_Appointment`, `Patient_ID`, `Resource_ID`, `Scheduling_Location_ID` |  |
| `PM.Cancellation_Reasons` | 9 | Appointments; PDF export | lookup | `Cancellation_Reason_ID` |  |
| `PM.Carriers` | 349 | Overview; PDF export | lookup | `Carrier_ID` | Name / phone only; Elig_Password never read |
| `PM.Contacts` | 31,024 | Overview; PDF export | data | `Contact_ID` | Policy-holder names only; SSN, Drivers_License_No never read |
| `PM.Diagnosis_Codes` | 89,862 | Overview; PDF export | lookup | `Diagnosis_Code_ID` |  |
| `PM.Incoming_Referral_Diags` | 1,275 | Overview; PDF export | data | `Diagnosis_Code_ID`, `Incoming_Referral_ID` |  |
| `PM.Incoming_Referrals` | 4,805 | Overview; PDF export | data | `Incoming_Referral_ID`, `Patient_ID`, `Patient_Policy_ID`, `Referred_From_Practitioner_ID`, `Referred_To_Practitioner_ID` |  |
| `PM.Insurance_Plans` | 4,306 | Overview; PDF export | lookup | `Insurance_Plan_ID` |  |
| `PM.Patient_Policies` | 24,276 | Overview; PDF export | data | `Patient_ID`, `Patient_Policy_ID`, `Policy_ID` |  |
| `PM.Patients` | 21,330 | CLI build-crosswalk (patient links); PDF export; Patient header; Print | join | `Account_ID`, `Patient_ID`, `Patient_Number` | EMR ↔ PM link (crosswalk build, PM account) |
| `PM.Policies` | 24,462 | Overview; PDF export | data | `Carrier_ID`, `Contact_ID`, `Insurance_Plan_ID`, `Policy_ID` |  |
| `PM.Practitioners` | 1,538 | Overview; PDF export | lookup | `Practitioner_ID` | Names only; SSN, Federal_ID_No never read |
| `PM.Resources` | 11 | Appointments; PDF export | lookup | `Resource_ID` |  |
| `PM.Scheduling_Locations` | 2 | Appointments; PDF export | lookup | `Scheduling_Location_ID` |  |

---

## 4. DMZ (pre-2010 legacy chart): only when `FEATURE_LEGACY_DMZ` is on

| Schema.Table | Rows | Used by screen(s) | Purpose | Key columns (join / filter) | Notes |
|---|---|---|---|---|---|
| `Encounters.MRC` | 277 | Chart notes; Documents; Lab results; Overview; Past history; Vitals | lookup | `mrc_key` |  |
| `Encounters.NoteResultLink` | 89,968 | Chart notes | join | `note_id` |  |
| `Medications.MedicationSigWorkTable` | 10,519 | Medications; Overview | lookup | `sig_key` |  |
| `Medications.MedicationStatus` | 11 | Medications; Overview | lookup | `MEMR_Med_Status` |  |
| `Medications.MedispanDrugs` | 72,460 | Medications; Overview | lookup | `drug_key` |  |
| `Medications.PatientMedications` | 201,155 | Medications; Overview | data | `amt_uom_key`, `drno`, `dxcode`, `mdrug_key`, `med_stat_key`, `patkey` … |  |
| `Medications.UserDrugs` | 918 | Medications; Overview | lookup | `drug_key` |  |
| `Orders.LabOrders` | 24,232 | Chart notes; Lab results; Overview | data | `drordering`, `faccode`, `patkey`, `sysorderno` |  |
| `Orders.LabTests` | 95,366 | Chart notes; Lab results; Overview | join | `sysorderno`, `systestno`, `systestorderno` |  |
| `Orders.TaskQueueComments` | 49,814 | Chart notes; Lab results; Overview | data | `order_or_result_no` | Large: `comment nvarchar(max)` |
| `Orders.Tests` | 847 | Chart notes; Lab results; Overview | lookup | `systestno` |  |
| `Patient.Consent` | 11 | Overview | data | `patkey` |  |
| `Procedures.PatientProcedures` | 9 | Overview; Past history | data | `drno`, `patkey`, `proc_status_key`, `proccode` |  |
| `Procedures.ProcedureStatus` | 6 | Overview; Past history | lookup | `MEMR_Proc_Status` |  |
| `Procedures.ProceduresMaster` | 226 | Overview; Past history | lookup | `proccode` |  |
| `conv.cac_adv_reactions` | 21 | Overview; Problems & allergies | lookup | `adv_reaction_key` |  |
| `conv.cac_alrg_cat` | 5 | Overview; Problems & allergies | lookup | `alrg_cat_key` |  |
| `conv.cac_alrg_code` | 894 | Overview; Problems & allergies | lookup | `alrg_code_key` |  |
| `conv.cac_alrg_status` | 4 | Overview; Problems & allergies | lookup | `alrg_stat_key` |  |
| `conv.cac_amt_uom` | 78 | Medications; Overview | lookup | `amt_uom_key` |  |
| `conv.cac_chrt_header` | 264,990 | Chart notes; Documents; Lab results; Overview; Past history; Print; Vitals | data | `drno`, `faccode`, `mrc_key`, `note_id`, `patkey` |  |
| `conv.cac_chrt_rtf` | 242,438 | Chart notes; Documents; Lab results; Overview; Past history; Print; Vitals | data | `note_id` | Large: `note_text nvarchar(max)` |
| `conv.cac_clin_refitem` | 229 | Lab results; Overview; Vitals | lookup | `clin_refitem_key` |  |
| `conv.cac_control_values` | 163 | Overview; Problems & allergies | lookup | `lookup_key` |  |
| `conv.cac_diaglink` | 120,846 | Chart notes; Lab results; Overview | data | `dxcode`, `systestorderno` |  |
| `conv.cac_pat_alrg` | 10,408 | Overview; Problems & allergies | data | `alrg_cat_key`, `alrg_code_key`, `alrg_stat_key`, `drno`, `pat_alrg_key`, `patkey` … |  |
| `conv.cac_pat_alrg_det` | 630 | Overview; Problems & allergies | data | `adv_reaction_key`, `pat_alrg_key` |  |
| `conv.cac_pat_pharm_pref` | 4,201 | Overview | data | `patkey` |  |
| `conv.cac_pat_photo` | 4,658 | Overview; header | data | `patkey` | Large: `photo image(2147483647)` |
| `conv.cac_pat_prob` | 32,018 | Overview; Problems & allergies | data | `drno`, `dxcode`, `patkey` |  |
| `conv.cac_patclin_item` | 589,381 | Lab results; Overview; Vitals | data | `clin_refitem_key`, `error_flag`, `patkey` |  |
| `conv.cac_rescom` | 61,787 | Chart notes; Lab results; Overview | data | `sysresultno` | Large: `comments nvarchar(max)` |
| `conv.cac_results` | 364,065 | Chart notes; Lab results; Overview | data | `sysresultno`, `systestordered` | Large: `comments nvarchar(max)` |
| `conv.drmast` | 845 | Chart notes; Documents; Lab results; Medications; Overview; Past history; Problems & allergies; Vitals; header | lookup | `drno` | Names / title only; ssno, dea_num never read |
| `conv.dxmast` | 15,629 | Chart notes; Lab results; Medications; Overview; Problems & allergies | lookup | `dxcode` |  |
| `conv.facmast` | 2,797 | Chart notes; Documents; Lab results; Overview; Past history; Vitals; header | lookup | `faccode` |  |
| `conv.pat_ext_info` | 25,335 | Overview | data | `patkey` |  |
| `conv.patgroup` | 23,874 | Overview; header | join | `drno`, `faccode`, `patkey` |  |
| `conv.patnotes` | 8,548 | Account notes; Overview | data | `patkey` |  |
| `conv.person` | 9,868 | Overview; header; patient list | data | `birthdate`, `fname`, `lname`, `patid`, `personkey` | ssno never read |
| `conv.pharmmast` | 203 | Overview | lookup | `pharmid` |  |
| `dbo.Gloss_base` | 80,602 | Overview; Past history | data | `drno`, `patkey` | Large: `ChartText varchar(max)` |
| `dbo.Resultsmigratetbl` | 24,164 | Chart notes; Lab results; Overview | data | `sysorderno` | Only for lab order / service / result dates |
| `dbo.ScannedImages` | 171,253 | Documents; Overview | data | `Errorflag`, `Imageid`, `drno`, `patkey` |  |
| `dbo.TestResultOrdertbl` | 95,190 | Chart notes; Lab results; Overview | data | `systestorderno` | Large: `testComments varchar(max)`; Only for collected dates and test comments |

Screens here are the separate **Pre-2010 records** section (`/legacy/...`).

---

## 5. Screen → tables

| Screen | Tables (schema.table) |
|---|---|
| Dashboard / patient list | `HPSITE.CONTACT`, `HPSITE.DEMOGRAPHICS`, `HPSITE.ENCOUNTER`, `HPSITE.PATIENT_IDENTIFIER`, `HPSITE.PATIENT_MERGE_HISTORY` |
| Patient header | `HPSITE.ADDRESSES`, `HPSITE.DEMOGRAPHICPICTURE`, `HPSITE.DEMOGRAPHICS`, `HPSITE.INSURANCECARRIERS`, `HPSITE.INSURANCES`, `HPSITE.PATIENT_IDENTIFIER`, `PM.Accounts (PM)`, `PM.Patients (PM)` |
| Overview | `HPSITE.ADDRESSES`, `HPSITE.CONTACT`, `HPSITE.DEMGUARANTOR`, `HPSITE.DEMOGRAPHICPICTURE`, `HPSITE.DEMOGRAPHICS`, `HPSITE.ENCOUNTER`, `HPSITE.HXDIAGNOSIS_ATTRIBUTES`, `HPSITE.HX_DIAGNOSIS`, `HPSITE.HX_MEDICATION`, `HPSITE.INSURANCECARRIERS`, `HPSITE.INSURANCES`, `HPSITE.LOCATION`, `HPSITE.MEDICATIONS`, `HPSITE.PATIENT_CONSENT`, `HPSITE.PATIENT_CONTACTS`, `HPSITE.PATIENT_ETHNICITY`, `HPSITE.PATIENT_PHYSICIANS`, `HPSITE.PATIENT_RACE`, `HPSITE.PROVIDERS`, `HPSITE.REMINDERS`, `PM.Carriers (PM)`, `PM.Contacts (PM)`, `PM.Diagnosis_Codes (PM)`, `PM.Incoming_Referral_Diags (PM)`, `PM.Incoming_Referrals (PM)`, `PM.Insurance_Plans (PM)`, `PM.Patient_Policies (PM)`, `PM.Policies (PM)`, `PM.Practitioners (PM)` |
| Visits | `HPSITE.CHART_ADDENDUM`, `HPSITE.CONTACT`, `HPSITE.DX`, `HPSITE.ENCOUNTER`, `HPSITE.ENCOUNTER_ASSESSMENT`, `HPSITE.ENCOUNTER_PLAN`, `HPSITE.HTML_DOCUMENTMAP`, `HPSITE.HTML_DOCUMENT_ORIG`, `HPSITE.LABORDERS`, `HPSITE.LOCATION`, `HPSITE.MEDICATIONS`, `HPSITE.NOTES_MASTER`, `HPSITE.NOTES_TEXTDATA`, `HPSITE.PROCEDURES`, `HPSITE.PROVIDERS`, `HPSITE.VITALS_DATA`, `HPSITE_ARCH.HTML_DOCUMENT_ARCH` |
| Appointments | `HPSITE.ARCH_SCHEDULE`, `HPSITE.LOCATION`, `HPSITE.PROVIDERS`, `PM.Appointment_Types (PM)`, `PM.Appointments (PM)`, `PM.Cancellation_Reasons (PM)`, `PM.Resources (PM)`, `PM.Scheduling_Locations (PM)` |
| Notes | `HPSITE.ENCOUNTER`, `HPSITE.HTML_DOCUMENTMAP`, `HPSITE.HTML_DOCUMENT_ORIG`, `HPSITE.MESSAGE_SAVED`, `HPSITE.NOTES_TEXTDATA`, `HPSITE.PROVIDERS`, `HPSITE.TRANSCRIPTION`, `HPSITE.TRANSCRIPTIONDATA`, `HPSITE.WEBMESSAGE`, `HPSITE.WEBMESSAGE_SAVED`, `HPSITE_ARCH.HTML_DOCUMENT_ARCH` |
| Notes (message names) | `HPSITE.DEMOGRAPHICS` |
| Problems & allergies | `HPSITE.ARCH_HXDIAGNOSIS`, `HPSITE.CONTACT`, `HPSITE.HXDIAGNOSIS_ATTRIBUTES`, `HPSITE.HX_DIAGNOSIS`, `HPSITE.PROVIDERS` |
| Medications | `HPSITE.HX_MEDICATION`, `HPSITE.MEDICATIONS`, `HPSITE.RXHUB_MED_HISTORY`, `HPSITE.RXHUB_REQUEST` |
| Lab results | `HPSITE.DX`, `HPSITE.LABCATALOG`, `HPSITE.LABORDERS`, `HPSITE.LAB_RESULT`, `HPSITE.PROVIDERS` |
| Vitals | `HPSITE.VITALS_DATA` |
| Documents | `HPSITE.CHARTATTACHMENT`, `HPSITE.HTML_DOCUMENT_ORIG`, `HPSITE.MESSAGE_SAVED`, `HPSITE.NOTES_RAWDATA`, `HPSITE.NOTES_TEXTDATA`, `HPSITE.PROVIDERS`, `HPSITE.SCAN_DOCUMENT`, `HPSITE.SCAN_DOCUMENTPAGE`, `HPSITE.SCAN_DOCUMENTTYPE`, `HPSITE.TRANSCRIPTION`, `HPSITE.TRANSCRIPTIONDATA`, `HPSITE.WEBMESSAGE`, `HPSITE.WEBMESSAGE_SAVED`, `HPSITE_ARCH.HTML_DOCUMENT_ARCH` |
| PDF export | `HPSITE.ADDRESSES`, `HPSITE.ARCH_SCHEDULE`, `HPSITE.CHARTATTACHMENT`, `HPSITE.CHART_ADDENDUM`, `HPSITE.CONTACT`, `HPSITE.DEMGUARANTOR`, `HPSITE.DEMOGRAPHICPICTURE`, `HPSITE.DEMOGRAPHICS`, `HPSITE.DX`, `HPSITE.ENCOUNTER`, `HPSITE.ENCOUNTER_ASSESSMENT`, `HPSITE.ENCOUNTER_PLAN`, `HPSITE.HTML_DOCUMENTMAP`, `HPSITE.HTML_DOCUMENT_ORIG`, `HPSITE.HXDIAGNOSIS_ATTRIBUTES`, `HPSITE.HX_DIAGNOSIS`, `HPSITE.HX_MEDICATION`, `HPSITE.INSURANCECARRIERS`, `HPSITE.INSURANCES`, `HPSITE.LABCATALOG`, `HPSITE.LABORDERS`, `HPSITE.LAB_RESULT`, `HPSITE.LOCATION`, `HPSITE.MEDICATIONS`, `HPSITE.MESSAGE_SAVED`, `HPSITE.NOTES_MASTER`, `HPSITE.NOTES_RAWDATA`, `HPSITE.NOTES_TEXTDATA`, `HPSITE.PATIENT_CONSENT`, `HPSITE.PATIENT_CONTACTS`, `HPSITE.PATIENT_ETHNICITY`, `HPSITE.PATIENT_IDENTIFIER`, `HPSITE.PATIENT_PHYSICIANS`, `HPSITE.PATIENT_RACE`, `HPSITE.PROCEDURES`, `HPSITE.PROVIDERS`, `HPSITE.REMINDERS`, `HPSITE.RXHUB_MED_HISTORY`, `HPSITE.RXHUB_REQUEST`, `HPSITE.SCAN_DOCUMENT`, `HPSITE.SCAN_DOCUMENTPAGE`, `HPSITE.SCAN_DOCUMENTTYPE`, `HPSITE.TRANSCRIPTION`, `HPSITE.TRANSCRIPTIONDATA`, `HPSITE.VITALS_DATA`, `HPSITE.WEBMESSAGE`, `HPSITE.WEBMESSAGE_SAVED`, `HPSITE_ARCH.HTML_DOCUMENT_ARCH`, `PM.Accounts (PM)`, `PM.Appointment_Types (PM)`, `PM.Appointments (PM)`, `PM.Cancellation_Reasons (PM)`, `PM.Carriers (PM)`, `PM.Contacts (PM)`, `PM.Diagnosis_Codes (PM)`, `PM.Incoming_Referral_Diags (PM)`, `PM.Incoming_Referrals (PM)`, `PM.Insurance_Plans (PM)`, `PM.Patient_Policies (PM)`, `PM.Patients (PM)`, `PM.Policies (PM)`, `PM.Practitioners (PM)`, `PM.Resources (PM)`, `PM.Scheduling_Locations (PM)` |
| Print | `HPSITE.ADDRESSES`, `HPSITE.CHART_ADDENDUM`, `HPSITE.CONTACT`, `HPSITE.DEMOGRAPHICPICTURE`, `HPSITE.DEMOGRAPHICS`, `HPSITE.ENCOUNTER`, `HPSITE.ENCOUNTER_PLAN`, `HPSITE.HTML_DOCUMENTMAP`, `HPSITE.HTML_DOCUMENT_ORIG`, `HPSITE.INSURANCECARRIERS`, `HPSITE.INSURANCES`, `HPSITE.LABORDERS`, `HPSITE.LOCATION`, `HPSITE.MEDICATIONS`, `HPSITE.MESSAGE_SAVED`, `HPSITE.NOTES_MASTER`, `HPSITE.NOTES_TEXTDATA`, `HPSITE.PATIENT_IDENTIFIER`, `HPSITE.PROCEDURES`, `HPSITE.PROVIDERS`, `HPSITE.TRANSCRIPTION`, `HPSITE.TRANSCRIPTIONDATA`, `HPSITE.VITALS_DATA`, `HPSITE.WEBMESSAGE`, `HPSITE.WEBMESSAGE_SAVED`, `HPSITE_ARCH.HTML_DOCUMENT_ARCH`, `PM.Accounts (PM)`, `PM.Patients (PM)` |
| Release log | `HPSITE.DEMOGRAPHICS`, `HPSITE.PHIREQUEST`, `HPSITE.PHIREQUEST_APPROVALSTATUS`, `HPSITE.PHIREQUEST_REQUESTEDINFO`, `HPSITE.PHIREQUEST_STATUS`, `HPSITE.PROVIDERS` |
| CLI build-crosswalk (patient links) | `HPSITE.DEMOGRAPHICS`, `HPSITE.EXTSYS_PATIENTINDEX`, `HPSITE.PATIENT_MERGE_HISTORY`, `PM.Patients (PM)` |
| CLI only | `HPSITE.CONTACT`, `HPSITE.DEMOGRAPHICS`, `HPSITE.ENCOUNTER`, `HPSITE.PATIENT_IDENTIFIER`, `HPSITE.PATIENT_MERGE_HISTORY` |
| Pre-2010 Account notes | `conv.patnotes` |
| Pre-2010 Chart notes | `Encounters.MRC`, `Encounters.NoteResultLink`, `Orders.LabOrders`, `Orders.LabTests`, `Orders.TaskQueueComments`, `Orders.Tests`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.cac_diaglink`, `conv.cac_rescom`, `conv.cac_results`, `conv.drmast`, `conv.dxmast`, `conv.facmast`, `dbo.Resultsmigratetbl`, `dbo.TestResultOrdertbl` |
| Pre-2010 Documents | `Encounters.MRC`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.drmast`, `conv.facmast`, `dbo.ScannedImages` |
| Pre-2010 Lab results | `Encounters.MRC`, `Orders.LabOrders`, `Orders.LabTests`, `Orders.TaskQueueComments`, `Orders.Tests`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.cac_clin_refitem`, `conv.cac_diaglink`, `conv.cac_patclin_item`, `conv.cac_rescom`, `conv.cac_results`, `conv.drmast`, `conv.dxmast`, `conv.facmast`, `dbo.Resultsmigratetbl`, `dbo.TestResultOrdertbl` |
| Pre-2010 Medications | `Medications.MedicationSigWorkTable`, `Medications.MedicationStatus`, `Medications.MedispanDrugs`, `Medications.PatientMedications`, `Medications.UserDrugs`, `conv.cac_amt_uom`, `conv.drmast`, `conv.dxmast` |
| Pre-2010 Overview | `Encounters.MRC`, `Medications.MedicationSigWorkTable`, `Medications.MedicationStatus`, `Medications.MedispanDrugs`, `Medications.PatientMedications`, `Medications.UserDrugs`, `Orders.LabOrders`, `Orders.LabTests`, `Orders.TaskQueueComments`, `Orders.Tests`, `Patient.Consent`, `Procedures.PatientProcedures`, `Procedures.ProcedureStatus`, `Procedures.ProceduresMaster`, `conv.cac_adv_reactions`, `conv.cac_alrg_cat`, `conv.cac_alrg_code`, `conv.cac_alrg_status`, `conv.cac_amt_uom`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.cac_clin_refitem`, `conv.cac_control_values`, `conv.cac_diaglink`, `conv.cac_pat_alrg`, `conv.cac_pat_alrg_det`, `conv.cac_pat_pharm_pref`, `conv.cac_pat_photo`, `conv.cac_pat_prob`, `conv.cac_patclin_item`, `conv.cac_rescom`, `conv.cac_results`, `conv.drmast`, `conv.dxmast`, `conv.facmast`, `conv.pat_ext_info`, `conv.patgroup`, `conv.patnotes`, `conv.person`, `conv.pharmmast`, `dbo.Gloss_base`, `dbo.Resultsmigratetbl`, `dbo.ScannedImages`, `dbo.TestResultOrdertbl` |
| Pre-2010 Past history | `Encounters.MRC`, `Procedures.PatientProcedures`, `Procedures.ProcedureStatus`, `Procedures.ProceduresMaster`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.drmast`, `conv.facmast`, `dbo.Gloss_base` |
| Pre-2010 Print | `conv.cac_chrt_header`, `conv.cac_chrt_rtf` |
| Pre-2010 Problems & allergies | `conv.cac_adv_reactions`, `conv.cac_alrg_cat`, `conv.cac_alrg_code`, `conv.cac_alrg_status`, `conv.cac_control_values`, `conv.cac_pat_alrg`, `conv.cac_pat_alrg_det`, `conv.cac_pat_prob`, `conv.drmast`, `conv.dxmast` |
| Pre-2010 Vitals | `Encounters.MRC`, `conv.cac_chrt_header`, `conv.cac_chrt_rtf`, `conv.cac_clin_refitem`, `conv.cac_patclin_item`, `conv.drmast`, `conv.facmast` |
| Pre-2010 header | `conv.cac_pat_photo`, `conv.drmast`, `conv.facmast`, `conv.patgroup`, `conv.person` |
| Pre-2010 patient list | `conv.person` |

Code labels (sex, visit types, statuses, race, consents …) are **not** read from `hpsystem.DICTIONARIES_MASTER` /
`HPSITE.DICTIONARIES_SITE` at run time. Their values were copied once into `config/*.yaml`, so those tables
aren't in the inventory.

### Sensitive columns

These columns exist in tables the app reads, and **none of them is referenced in any query** (select, join,
filter or sort). The app also never connects to `AIE_Master`.

| Column | Referenced by the app |
|---|---|
| `EMR.HPSITE.DEMGUARANTOR.GUARANTOR_SSNUM` | no |
| `EMR.HPSITE.DEMOGRAPHICS.DEM_SSNUM` | no |
| `EMR.HPSITE.EXTSYS_PATIENTINDEX.SSN` | no |
| `EMR.HPSITE.EXTSYS_PATIENTINDEX.DRIVERLICENSENUMBER` | no |
| `EMR.HPSITE.EXTSYS_PATIENTINDEX.DRIVERLICENSESTATE` | no |
| `EMR.HPSITE.INSURANCES.INS_SUBSSNUM` | no |
| `EMR.HPSITE.PROVIDERS.PROV_SSNUM` | no |
| `EMR.HPSITE.PROVIDERS.PROV_PASSWORD` | no |
| `EMR.HPSITE.PROVIDERS.PROV_LASTPASSWORDCHANGE` | no |
| `EMR.HPSITE.PROVIDERS.PROV_DEAID` | no |
| `Ntier_0010060.PM.Carriers.Elig_Output_User_Password` | no |
| `Ntier_0010060.PM.Carriers.Elig_Password` | no |
| `Ntier_0010060.PM.Contacts.SSN` | no |
| `Ntier_0010060.PM.Contacts.Drivers_License_No` | no |
| `Ntier_0010060.PM.Practitioners.SSN` | no |
| `DMZ.conv.drmast.dea_num` | no |
| `DMZ.conv.drmast.ssno` | no |
| `DMZ.conv.person.ssno` | no |
| `Ntier_0010060.PM.Practitioners.Federal_ID_No` | no |

---

## 6. Query scoping and findings

Every chart query filters on the patient's indexed column (`:emr_id`, `:ntier_id` or `:person_key`). The SQL files
with **no direct patient filter** are below, each with the reason it is safe:

| SQL file | Why it is safe |
|---|---|
| `dmz/legacy_patient_search.sql` | Pre-2010 patient list search: paged, filtered by name / DOB / legacy id |
| `emr/crosswalk_emr_ntier.sql` | CLI `build-crosswalk` only (offline batch, IDs only); never on a web request |
| `emr/encounter_text_notes.sql` | Filtered by encounter id, run only after `encounter_header.sql` confirmed the encounter belongs to the patient |
| `emr/patient_merges.sql` | CLI `build-crosswalk` only (289 merge rows); never on a web request |
| `emr/patient_search.sql` | Patient list search: paged (`OFFSET … FETCH 25`), filtered by name / DOB / chart id |
| `emr/phi_request_info.sql` | Release log: the whole 110-row table, cached 24 h |
| `emr/phi_requests.sql` | Release log: the whole 659-row table, cached 24 h |
| `emr/visit_addenda.sql` | Filtered by encounter id after the same ownership check |
| `emr/visit_assessment.sql` | Filtered by encounter id after `visit_one.sql` (patient + contact) matched |
| `emr/visit_plan.sql` | Filtered by encounter id after the ownership check |
| `emr/visit_text_notes.sql` | Filtered by contact id after `visit_one.sql` (patient + contact) matched |
| `emr/visits_diagnoses.sql` | Filtered by the encounter ids of the patient's own visit page |

**Findings:**
- **Missing columns:** none. All 690 referenced columns exist.
- **Sensitive columns selected:** none.
- **Unused query:** `emr/transcriptions.sql` (`emr.transcriptions` → `live.notes`) is called only by
  `app/services/notes.py::notes_tab`, the original Notes tab, which `notes_service.notes_tab` replaced. The
  Notes tab reads dictations through `notes_list_trans.sql` instead. It's safe to remove in a cleanup.
- **Data-quality notes:** a few lookups have no labels in the database and use `config/*.yaml` values marked
  TODO (pre-2010 problem status, referral status, PM patient type). See PRE2010_RECORDS.md and DATA_MAP.md.

---

## 7. Databases on the server that the app never touches

Based on the code scan (no SQL file, repository or setting refers to them):

| Database | Note |
|---|---|
| `AIE_Master` | Interface engine: **never** to be read (credentials) |
| `ATP` | 57 GB, not part of the chart |
| `CDS_EMRTRAIN` | Training |
| `EMRTRAIN` | Training copy of the EHR |
| `FORMULARY` | Drug formulary reference data (208 GB) |
| `HPI2010_SDC102` | Setup / conversion |
| `IMO` | Terminology reference |
| `InstallationManager` | Allscripts installer |
| `MDRX_CHAT` | Messaging |
| `MEDISPAN` | Drug reference |
| `PRO_ADMIN` | Administration |
| `Psrx` | Prescribing |
| `master`, `model`, `msdb`, `tempdb` | SQL Server system databases (the app only reads catalog views for `/readyz` and `dbcheck`) |

---

## 8. The app's own database (PostgreSQL)

Not part of the Allscripts data: created by Alembic, written only by the app.

| Table | Columns | Purpose |
|---|---|---|
| `users` | id, email, full_name, password_hash, is_active, failed_attempts, locked_until, created_at, last_login_at | Staff accounts (argon2id hashes) |
| `sessions` | id (hashed token), user_id, created_at, last_seen_at, expires_at, ip, user_agent | Server-side sessions |
| `audit_log` | id, at, user_id, action, patient_key, detail, ip, request_id | Every sign-in, search, view, print and export (append-only) |
| `release_log` | id, at, user_id, patient_key, sections, date_from, date_to, recipient, page_count, file_sha256, release_code, purpose | Every PDF release (append-only) |
| `patient_crosswalk` | patient_key, emr_id, ntier_id, dmz_id, match_method, confidence, built_at | EMR ↔ PM ↔ pre-2010 patient links (built by `cli.py build-crosswalk`) |
| `export_selection` | id, session_id, patient_key, item_type, item_id, added_at | Items added to an export (per session) |

