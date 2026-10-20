-- Pre-2010 records: the legacy patient's external identifiers (other systems' patient numbers).
SELECT
    RTRIM(e.ext_id) AS ext_id,
    RTRIM(e.alt_id) AS alt_id,
    RTRIM(e.send_source) AS source,
    e.log_datetime AS recorded_at
FROM conv.pat_ext_info AS e
WHERE e.patkey = :person_key
