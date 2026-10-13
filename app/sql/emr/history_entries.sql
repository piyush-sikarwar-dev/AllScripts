-- Problems & allergies tab: current state of every history entry of the patient (latest revision
-- of each HXDIAGNOSIS_ID), with the provider of the visit it was recorded in (CONTACT_ID).
WITH latest AS (
    SELECT
        h.HXDIAGNOSIS_ID,
        h.CATEGORY_CODE,
        h.SOURCE,
        h.SOURCE_CODE,
        h.TITLE,
        h.DESCRIPTION,
        h.ACTIVITY_CODE,
        h.SIGNIFICANCE_CODE,
        h.ACUITY_CODE,
        h.ONSET_DATE,
        h.ONSETDATEMASK_CODE,
        h.RESOLVED_DATE,
        h.COMMENTS,
        h.BASIS,
        h.REASONOFCHANGE,
        h.TAG_SYSTEMDATE,
        h.CONTACT_ID,
        h.IMO_CODE,
        ROW_NUMBER() OVER (PARTITION BY h.HXDIAGNOSIS_ID ORDER BY h.TAG_REVISION DESC) AS rn
    FROM HPSITE.HX_DIAGNOSIS AS h
    WHERE h.PATIENT_ID = :emr_id
)
SELECT
    l.HXDIAGNOSIS_ID AS hx_id,
    l.CATEGORY_CODE AS category_code,
    l.SOURCE AS code_system,
    l.SOURCE_CODE AS code,
    l.TITLE AS title,
    l.DESCRIPTION AS description,
    l.ACTIVITY_CODE AS activity_code,
    l.SIGNIFICANCE_CODE AS significance_code,
    l.ACUITY_CODE AS acuity_code,
    l.ONSET_DATE AS onset,
    l.ONSETDATEMASK_CODE AS onset_mask,
    l.RESOLVED_DATE AS resolved,
    l.COMMENTS AS comments,
    l.BASIS AS basis,
    l.REASONOFCHANGE AS reason,
    l.TAG_SYSTEMDATE AS recorded,
    l.IMO_CODE AS imo_code,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM latest AS l
LEFT JOIN HPSITE.CONTACT AS c
    ON c.IMRECONTACT_CODE = l.CONTACT_ID
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = c.IMREPROV_CODE
WHERE l.rn = 1
