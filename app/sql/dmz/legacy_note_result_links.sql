-- Pre-2010 records: which lab tests each of the legacy patient's chart notes reports
-- (Encounters.NoteResultLink; the "ORDER MANAGEMENT RESULT" notes have no text of their own).
SELECT
    l.note_id,
    l.systestorderno AS test_id
FROM conv.cac_chrt_header AS h
JOIN Encounters.NoteResultLink AS l
    ON l.note_id = h.note_id
WHERE h.patkey = :person_key
