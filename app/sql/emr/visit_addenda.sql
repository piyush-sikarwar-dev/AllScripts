-- Addenda of an encounter with their note text (latest revision).
SELECT
    a.ADDENDUM_DT AS added,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    t.NOTE_TEXT AS note_text
FROM HPSITE.CHART_ADDENDUM AS a
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = a.IMREPROV_CODE
OUTER APPLY (
    SELECT TOP 1 n.NOTE_TEXT
    FROM HPSITE.NOTES_TEXTDATA AS n
    WHERE n.IMRENOTE_CODE = a.IMRENOTE_CODE
    ORDER BY n.TAG_REVISION DESC
) AS t
WHERE a.IMREENC_CODE = :encounter_id
