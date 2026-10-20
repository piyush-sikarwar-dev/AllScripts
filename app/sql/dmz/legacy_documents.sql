-- Pre-2010 records: scanned documents of the legacy patient (metadata only; the file path is read
-- one document at a time by legacy_document_file.sql).
SELECT
    s.Imageid AS document_id,
    s.DocDate AS doc_date,
    s.scanneddate AS scanned_date,
    RTRIM(s.MRCName) AS doc_type,
    s.ipages AS pages,
    RTRIM(s.FileExt) AS file_ext,
    s.noteid AS note_id,
    RTRIM(dr.lname) AS provider_last,
    RTRIM(dr.fname) AS provider_first,
    RTRIM(dr.title) AS provider_title
FROM dbo.ScannedImages AS s
LEFT JOIN conv.drmast AS dr
    ON dr.drno = s.drno
WHERE s.patkey = :person_key
  AND ISNULL(s.Errorflag, 0) = 0
