-- Dictations / transcriptions for a patient, excluding those marked erroneous.
SELECT
    t.TRANSCRIPTION_ID AS transcription_id,
    t.DICTATED_DT AS dictated,
    t.TRANSCRIBED_DT AS transcribed,
    t.ENCOUNTER_DATE AS encounter_date,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM HPSITE.TRANSCRIPTION AS t
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = t.IMREPROV_CODE
WHERE t.IMREDEM_CODE = :emr_id
  AND t.MARK_ERRONEOUS_DT IS NULL
