-- One row per EMR patient x matching Ntier patient (EMR.EXTSYS_PATIENTINDEX.PATIENTID = PM.Patients.Patient_Number).
-- IDs only: no names, DOBs or other PHI leave the database.
SELECT
    d.IMREDEM_CODE AS emr_id,
    p.Patient_ID AS ntier_id,
    p.Active_Patient_ID AS ntier_active_id
FROM EMR.HPSITE.DEMOGRAPHICS AS d
LEFT JOIN EMR.HPSITE.EXTSYS_PATIENTINDEX AS x
    ON x.IMREDEM_CODE = d.IMREDEM_CODE
LEFT JOIN Ntier_0010060.PM.Patients AS p
    ON LTRIM(RTRIM(p.Patient_Number)) COLLATE DATABASE_DEFAULT
     = LTRIM(RTRIM(x.PATIENTID)) COLLATE DATABASE_DEFAULT
