-- Plain-text notes of all non-cancelled contacts of one encounter (latest revision each), in
-- contact start order. Ownership of the encounter is checked before this runs.
SELECT
    c.IMRECONTACT_CODE AS contact_id,
    c.CON_START AS contact_start,
    nm.IMRENOTE_CODE AS note_id,
    t.NOTE_TYPE AS note_type,
    t.NOTE_TEXT AS note_text
FROM HPSITE.CONTACT AS c
JOIN HPSITE.NOTES_MASTER AS nm
    ON nm.IMRECONTACT_CODE = c.IMRECONTACT_CODE
CROSS APPLY (
    SELECT TOP 1 n.NOTE_TYPE, n.NOTE_TEXT
    FROM HPSITE.NOTES_TEXTDATA AS n
    WHERE n.IMRENOTE_CODE = nm.IMRENOTE_CODE
    ORDER BY n.TAG_REVISION DESC
) AS t
WHERE c.IMREENC_CODE = :encounter_id
  AND ISNULL(c.CON_CANCELED, 0) = 0
