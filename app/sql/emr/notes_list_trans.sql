-- Notes tab index: the patient's dictations (metadata only), excluding those marked erroneous,
-- with the dictating provider and the patient's own encounter (if the encounter exists).
SELECT
    t.TRANSCRIPTION_ID AS transcription_id,
    t.DICTATED_DT AS dictated,
    t.TRANSCRIBED_DT AS transcribed,
    t.ENCOUNTER_DATE AS encounter_date,
    t.transtype_code AS trans_type,
    e.IMREENC_CODE AS encounter_id,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM HPSITE.TRANSCRIPTION AS t
LEFT JOIN HPSITE.ENCOUNTER AS e
    ON e.IMREENC_CODE = t.IMREENC_CODE
   AND e.IMREDEMEC_CODE = t.IMREDEM_CODE
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = t.IMREPROV_CODE
WHERE t.IMREDEM_CODE = :emr_id
  AND t.MARK_ERRONEOUS_DT IS NULL
