-- The text (RTF) of one chart attachment of this patient, latest revision.
SELECT TOP 1
    t.NOTE_TEXT AS note_text
FROM HPSITE.CHARTATTACHMENT AS c
JOIN HPSITE.NOTES_TEXTDATA AS t
    ON t.IMRENOTE_CODE = c.IMRENOTE_CODE
WHERE c.IMRENOTE_CODE = :attachment_id
  AND c.IMREDEMEC_CODE = :emr_id
  AND ISNULL(c.TAG_ARCHIVED, 0) = 0
ORDER BY t.TAG_REVISION DESC
