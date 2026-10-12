-- Prescriptions: latest revision of each medication.
WITH latest AS (
    SELECT
        m.IMREMED_CODE,
        m.MED_TITLE,
        m.MED_DOSE,
        m.MED_DOSEUNIT,
        m.MED_ROUTE,
        m.MED_FREQUENCY,
        m.MED_INTAKE,
        m.MED_STARTDATE,
        m.MED_STARTDATEMASK,
        m.MED_ENDDATE,
        m.MED_ENDDATEMASK,
        m.MED_STATUS,
        ROW_NUMBER() OVER (PARTITION BY m.IMREMED_CODE ORDER BY m.TAG_REVISION DESC) AS rn
    FROM HPSITE.MEDICATIONS AS m
    WHERE m.IMREDEMEC_CODE = :emr_id
)
SELECT
    IMREMED_CODE AS med_id,
    MED_TITLE AS title,
    MED_DOSE AS dose,
    MED_DOSEUNIT AS dose_unit,
    MED_ROUTE AS route,
    MED_FREQUENCY AS frequency,
    MED_INTAKE AS intake,
    MED_STARTDATE AS start_date,
    MED_STARTDATEMASK AS start_mask,
    MED_ENDDATE AS end_date,
    MED_ENDDATEMASK AS end_mask,
    MED_STATUS AS status_code
FROM latest
WHERE rn = 1
