-- The file of one chart attachment of this patient (bytes + format), latest copy.
SELECT TOP 1
    r.NOTE_DATA AS content,
    r.NOTE_SUBFORMAT AS file_format
FROM HPSITE.CHARTATTACHMENT AS c
JOIN HPSITE.NOTES_RAWDATA AS r
    ON r.IMRENOTE_CODE = c.IMRENOTE_CODE
WHERE c.IMRENOTE_CODE = :attachment_id
  AND c.IMREDEMEC_CODE = :emr_id
  AND ISNULL(c.TAG_ARCHIVED, 0) = 0
ORDER BY r.TAG_SYSTEMDATE DESC
