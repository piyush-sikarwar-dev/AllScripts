-- Problems / allergies / surgical / family / social history: latest revision of each item.
WITH latest AS (
    SELECT
        h.HXDIAGNOSIS_ID,
        h.CATEGORY_CODE,
        h.TITLE,
        h.SOURCE,
        h.SOURCE_CODE,
        h.ONSET_DATE,
        h.ONSETDATEMASK_CODE,
        h.RESOLVED_DATE,
        h.ACTIVITY_CODE,
        ROW_NUMBER() OVER (PARTITION BY h.HXDIAGNOSIS_ID ORDER BY h.TAG_REVISION DESC) AS rn
    FROM HPSITE.HX_DIAGNOSIS AS h
    WHERE h.PATIENT_ID = :emr_id
)
SELECT
    HXDIAGNOSIS_ID AS hx_id,
    CATEGORY_CODE AS category_code,
    TITLE AS title,
    SOURCE AS code_system,
    SOURCE_CODE AS code,
    ONSET_DATE AS onset,
    ONSETDATEMASK_CODE AS onset_mask,
    RESOLVED_DATE AS resolved,
    ACTIVITY_CODE AS activity_code
FROM latest
WHERE rn = 1
