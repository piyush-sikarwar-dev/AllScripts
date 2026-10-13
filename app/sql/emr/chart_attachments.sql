-- Documents tab: chart attachments of the patient (HPSITE.CHARTATTACHMENT; one row per note
-- code). The file itself lives in NOTES_RAWDATA (PDF, TIFF, images) and is not read here; a few
-- attachments only have RTF text in NOTES_TEXTDATA. Archived rows are hidden.
SELECT
    c.IMRENOTE_CODE AS attachment_id,
    c.CHAT_DATE AS attached,
    c.CHAT_DATEMASK AS date_mask,
    c.CHAT_CONTENT AS content_type,
    c.CHAT_SUBJECT AS subject,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title,
    f.NOTE_SUBFORMAT AS file_format,
    tx.has_text
FROM HPSITE.CHARTATTACHMENT AS c
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = c.IMREPROV_CODE
OUTER APPLY (
    SELECT TOP 1 r.NOTE_SUBFORMAT
    FROM HPSITE.NOTES_RAWDATA AS r
    WHERE r.IMRENOTE_CODE = c.IMRENOTE_CODE
    ORDER BY r.TAG_SYSTEMDATE DESC
) AS f
OUTER APPLY (
    SELECT TOP 1 1 AS has_text
    FROM HPSITE.NOTES_TEXTDATA AS t
    WHERE t.IMRENOTE_CODE = c.IMRENOTE_CODE
) AS tx
WHERE c.IMREDEMEC_CODE = :emr_id
  AND ISNULL(c.TAG_ARCHIVED, 0) = 0
