-- All clinical documents for a patient (metadata only) for the Notes tab.
SELECT
    d.DOCUMENT_ID AS document_id,
    d.TITLE AS title,
    d.AUTHOR AS author,
    d.CREATED_DATE AS created,
    d.STATUS AS status_code
FROM HPSITE.HTML_DOCUMENT_ORIG AS d
WHERE d.PATIENT_ID = :emr_id
