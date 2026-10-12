-- Clinical documents linked to an encounter (metadata only; content is fetched on demand).
SELECT
    d.DOCUMENT_ID AS document_id,
    d.TITLE AS title,
    d.AUTHOR AS author,
    d.CREATED_DATE AS created
FROM HPSITE.HTML_DOCUMENTMAP AS m
JOIN HPSITE.HTML_DOCUMENT_ORIG AS d
    ON d.DOCUMENT_ID = m.DOCUMENT_ID
WHERE m.SOURCE = 'IMREENC_CODE'
  AND m.SOURCE_CODE = :encounter_code
  AND d.PATIENT_ID = :emr_id
