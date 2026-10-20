-- Pre-2010 records: the legacy patient's recorded clinical values (labs and vitals) with the item
-- name from the catalog. Rows flagged in error are left out. The service splits labs from vitals.
SELECT
    c.pat_clin_item_id AS item_id,
    c.service_datetime,
    RTRIM(r.name) AS item_name,
    RTRIM(c.clin_ref_value) AS value,
    RTRIM(c.reflow) AS ref_low,
    RTRIM(c.refhigh) AS ref_high,
    RTRIM(c.comments) AS comments,
    c.note_id
FROM conv.cac_patclin_item AS c
JOIN conv.cac_clin_refitem AS r
    ON r.clin_refitem_key = c.clin_refitem_key
WHERE c.patkey = :person_key
  AND ISNULL(c.error_flag, 'N') <> 'Y'
