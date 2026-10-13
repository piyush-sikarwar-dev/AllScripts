-- Classification sources of the patient's documents: which HTML_DOCUMENTMAP.SOURCE names (from
-- config/note_categories.yaml) each document has. Only SOURCE names are read, never SOURCE_CODE.
SELECT DISTINCT
    m.DOCUMENT_ID AS document_id,
    m.SOURCE AS source
FROM HPSITE.HTML_DOCUMENTMAP AS m
JOIN HPSITE.HTML_DOCUMENT_ORIG AS d
    ON d.DOCUMENT_ID = m.DOCUMENT_ID
WHERE d.PATIENT_ID = :emr_id
  AND m.SOURCE IN :sources
