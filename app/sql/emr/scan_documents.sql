-- Scanned documents for one patient (metadata + page count). Erroneous ones (SCANSTATUS 10)
-- are filtered in the repository via config/statuses.yaml.
SELECT
    d.DOCUMENT_ID AS document_id,
    d.DOCUMENT_DT AS document_date,
    d.TITLE AS title,
    t.DESCRIPTION AS type,
    d.SCANSTATUS_CODE AS status_code,
    (SELECT COUNT(1) FROM HPSITE.SCAN_DOCUMENTPAGE AS p WHERE p.DOCUMENT_ID = d.DOCUMENT_ID) AS pages
FROM HPSITE.SCAN_DOCUMENT AS d
LEFT JOIN HPSITE.SCAN_DOCUMENTTYPE AS t
    ON t.SCAN_ID = d.SCAN_ID
WHERE d.IMREDEM_CODE = :emr_id
