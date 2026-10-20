-- Pre-2010 records: the RTF text of one chart note, only if it belongs to this legacy patient.
SELECT
    h.note_id,
    h.service_datetime AS service_date,
    r.rownum AS row_no,
    r.note_text
FROM conv.cac_chrt_header AS h
JOIN conv.cac_chrt_rtf AS r
    ON r.note_id = h.note_id
WHERE h.note_id = :note_id
  AND h.patkey = :person_key
ORDER BY r.rownum
