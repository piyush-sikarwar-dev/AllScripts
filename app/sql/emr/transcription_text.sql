-- One transcription's text (RTF), only if it belongs to the patient and is not erroneous.
SELECT
    t.TRANSCRIPTION_ID AS transcription_id,
    t.DICTATED_DT AS dictated,
    t.ENCOUNTER_DATE AS encounter_date,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    d.trans_data AS rtf
FROM HPSITE.TRANSCRIPTION AS t
JOIN HPSITE.TRANSCRIPTIONDATA AS d
    ON d.TRANSCRIPTION_ID = t.TRANSCRIPTION_ID
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = t.IMREPROV_CODE
WHERE t.TRANSCRIPTION_ID = :transcription_id
  AND t.IMREDEM_CODE = :emr_id
  AND t.MARK_ERRONEOUS_DT IS NULL
