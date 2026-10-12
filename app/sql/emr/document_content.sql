-- One document's content, only if it belongs to the patient. Most bodies were moved to the
-- archive table (same rule as Allscripts' HPSITE.HTML_DOCUMENT_VW view).
SELECT
    d.DOCUMENT_ID AS document_id,
    d.TITLE AS title,
    d.AUTHOR AS author,
    d.CREATED_DATE AS created,
    CASE WHEN DATALENGTH(d.DOCUMENT) > 0 THEN d.DOCUMENT ELSE a.DOCUMENT END AS content
FROM HPSITE.HTML_DOCUMENT_ORIG AS d
LEFT JOIN HPSITE_ARCH.HTML_DOCUMENT_ARCH AS a
    ON a.DOCUMENT_ID = d.DOCUMENT_ID
WHERE d.DOCUMENT_ID = :document_id
  AND d.PATIENT_ID = :emr_id
