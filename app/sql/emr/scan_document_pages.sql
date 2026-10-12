-- Pages of one scanned document, only if the document belongs to the patient.
-- FILELOCATION is a UNC path on \\amhs-db1\hmscan (mapped to SCAN_ROOT by the DocumentStore).
SELECT
    d.DOCUMENT_ID AS document_id,
    d.DOCUMENT_DT AS document_date,
    d.TITLE AS title,
    t.DESCRIPTION AS type,
    d.SCANSTATUS_CODE AS status_code,
    p.PAGE_ID AS page_id,
    p.PAGENUMBER AS page_number,
    p.FILELOCATION AS file_location
FROM HPSITE.SCAN_DOCUMENT AS d
LEFT JOIN HPSITE.SCAN_DOCUMENTTYPE AS t
    ON t.SCAN_ID = d.SCAN_ID
LEFT JOIN HPSITE.SCAN_DOCUMENTPAGE AS p
    ON p.DOCUMENT_ID = d.DOCUMENT_ID
WHERE d.DOCUMENT_ID = :document_id
  AND d.IMREDEM_CODE = :emr_id
ORDER BY p.PAGENUMBER, p.PAGE_ID
