-- Pre-2010 records: the legacy patient's chart notes (metadata only; the RTF text is read one
-- note at a time by legacy_note_text.sql), with the provider and facility names.
SELECT
    h.note_id,
    h.service_datetime AS service_date,
    RTRIM(d.lname) AS provider_last,
    RTRIM(d.fname) AS provider_first,
    RTRIM(d.title) AS provider_title,
    RTRIM(f.facname) AS facility,
    CASE WHEN EXISTS (SELECT 1 FROM conv.cac_chrt_rtf AS r WHERE r.note_id = h.note_id)
         THEN 1 ELSE 0 END AS has_text
FROM conv.cac_chrt_header AS h
LEFT JOIN conv.drmast AS d
    ON d.drno = h.drno
LEFT JOIN conv.facmast AS f
    ON f.faccode = h.faccode
WHERE h.patkey = :person_key
