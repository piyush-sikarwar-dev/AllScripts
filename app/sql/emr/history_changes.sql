-- Change history of ONE history entry of this patient: the revisions still in HX_DIAGNOSIS plus
-- the earlier ones in ARCH_HXDIAGNOSIS (the only place ARCH_* is read; never for current state).
-- (HXDIAGNOSIS_ID, TAG_REVISION) never repeats across the two tables (discovery 2026-10-13).
WITH revisions AS (
    SELECT
        h.TAG_REVISION, h.TAG_SYSTEMDATE, h.CONTACT_ID, h.TITLE, h.ACTIVITY_CODE,
        h.SIGNIFICANCE_CODE, h.ONSET_DATE, h.ONSETDATEMASK_CODE, h.RESOLVED_DATE, h.COMMENTS,
        h.REASONOFCHANGE
    FROM HPSITE.HX_DIAGNOSIS AS h
    WHERE h.HXDIAGNOSIS_ID = :hx_id
      AND h.PATIENT_ID = :emr_id
    UNION ALL
    SELECT
        a.TAG_REVISION, a.TAG_SYSTEMDATE, a.CONTACT_ID, a.TITLE, a.ACTIVITY_CODE,
        a.SIGNIFICANCE_CODE, a.ONSET_DATE, a.ONSETDATEMASK_CODE, a.RESOLVED_DATE, a.COMMENTS,
        a.REASONOFCHANGE
    FROM HPSITE.ARCH_HXDIAGNOSIS AS a
    WHERE a.HXDIAGNOSIS_ID = :hx_id
      AND a.PATIENT_ID = :emr_id
)
SELECT
    r.TAG_REVISION AS revision,
    r.TAG_SYSTEMDATE AS changed,
    r.TITLE AS title,
    r.ACTIVITY_CODE AS activity_code,
    r.SIGNIFICANCE_CODE AS significance_code,
    r.ONSET_DATE AS onset,
    r.ONSETDATEMASK_CODE AS onset_mask,
    r.RESOLVED_DATE AS resolved,
    r.COMMENTS AS comments,
    r.REASONOFCHANGE AS reason,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM revisions AS r
LEFT JOIN HPSITE.CONTACT AS c
    ON c.IMRECONTACT_CODE = r.CONTACT_ID
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = c.IMREPROV_CODE
ORDER BY r.TAG_REVISION, r.TAG_SYSTEMDATE
