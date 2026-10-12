-- Medication history: latest revision of each item.
WITH latest AS (
    SELECT
        h.HXMEDICATION_ID,
        h.TITLE,
        h.DOSE,
        h.DOSEUNIT,
        h.ROUTE,
        h.FREQUENCY,
        h.INTAKE,
        h.START_DATE,
        h.STARTDATEMASK_CODE,
        h.END_DATE,
        h.ENDDATEMASK_CODE,
        h.ACTIVITY_CODE,
        ROW_NUMBER() OVER (PARTITION BY h.HXMEDICATION_ID ORDER BY h.TAG_REVISION DESC) AS rn
    FROM HPSITE.HX_MEDICATION AS h
    WHERE h.PATIENT_ID = :emr_id
)
SELECT
    HXMEDICATION_ID AS hxmed_id,
    TITLE AS title,
    DOSE AS dose,
    DOSEUNIT AS dose_unit,
    ROUTE AS route,
    FREQUENCY AS frequency,
    INTAKE AS intake,
    START_DATE AS start_date,
    STARTDATEMASK_CODE AS start_mask,
    END_DATE AS end_date,
    ENDDATEMASK_CODE AS end_mask,
    ACTIVITY_CODE AS activity_code
FROM latest
WHERE rn = 1
