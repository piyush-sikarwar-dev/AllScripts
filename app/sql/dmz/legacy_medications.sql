-- Pre-2010 records: every medication entry of the legacy patient. Entries of one medication share
-- parent_key (new prescription → continued → discontinued); the service groups them.
-- Status labels and groups from Medications.MedicationStatus (PROEHR_Med_Status 1 active,
-- 3 discontinued, 6 entered in error, 2 deleted).
SELECT
    m.pat_med_key AS entry_id,
    m.parent_key AS med_id,
    RTRIM(md.disp_name) AS mdrug_name,
    RTRIM(ud.disp_name) AS udrug_name,
    RTRIM(ud.strength) AS udrug_strength,
    RTRIM(s.Quantity) AS sig_quantity,
    RTRIM(s.DoseForm) AS sig_dose_form,
    RTRIM(s.Frequency) AS sig_frequency,
    m.amt_dispensed,
    RTRIM(u.abbrev) AS amt_uom,
    m.num_refills,
    m.days_supply,
    RTRIM(m.disp_as_written) AS dispense_as_written,
    m.date_written,
    m.date_of_service,
    m.stop_date,
    m.last_dose_date,
    m.med_stat_key AS status_key,
    ms.MEMR_Med_Description AS status,
    ms.PROEHR_Med_Status AS status_group,
    RTRIM(m.comments) AS comments,
    RTRIM(m.dxcode) AS dx_code,
    RTRIM(dx.dxdesc1) AS dx_desc,
    RTRIM(dr.lname) AS provider_last,
    RTRIM(dr.fname) AS provider_first,
    RTRIM(dr.title) AS provider_title
FROM Medications.PatientMedications AS m
LEFT JOIN Medications.MedispanDrugs AS md
    ON md.drug_key = m.mdrug_key
LEFT JOIN Medications.UserDrugs AS ud
    ON ud.drug_key = m.udrug_key
LEFT JOIN Medications.MedicationSigWorkTable AS s
    ON s.sig_key = m.sig_key
LEFT JOIN conv.cac_amt_uom AS u
    ON u.amt_uom_key = m.amt_uom_key
LEFT JOIN Medications.MedicationStatus AS ms
    ON ms.MEMR_Med_Status = m.med_stat_key
LEFT JOIN conv.dxmast AS dx
    ON dx.dxcode = m.dxcode
LEFT JOIN conv.drmast AS dr
    ON dr.drno = m.drno
WHERE m.patkey = :person_key
