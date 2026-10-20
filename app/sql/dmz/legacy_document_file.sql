-- Pre-2010 records: the file location of one scanned document, only if it belongs to this patient.
SELECT
    s.Imageid AS document_id,
    s.fpath AS location,
    s.ipages AS pages,
    RTRIM(s.FileExt) AS file_ext
FROM dbo.ScannedImages AS s
WHERE s.Imageid = :document_id
  AND s.patkey = :person_key
  AND ISNULL(s.Errorflag, 0) = 0
