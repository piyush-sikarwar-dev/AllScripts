-- Plain-text notes attached to a contact (latest revision of each note).
SELECT
    nm.IMRENOTE_CODE AS note_id,
    t.NOTE_TYPE AS note_type,
    t.NOTE_TEXT AS note_text
FROM HPSITE.NOTES_MASTER AS nm
CROSS APPLY (
    SELECT TOP 1 n.NOTE_TYPE, n.NOTE_TEXT
    FROM HPSITE.NOTES_TEXTDATA AS n
    WHERE n.IMRENOTE_CODE = nm.IMRENOTE_CODE
    ORDER BY n.TAG_REVISION DESC
) AS t
WHERE nm.IMRECONTACT_CODE = :contact_id
