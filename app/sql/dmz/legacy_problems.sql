-- Pre-2010 records: the legacy patient's problem list (ICD-9) with descriptions and provider.
SELECT
    p.pat_prob_key AS problem_id,
    RTRIM(p.dxcode) AS dx_code,
    RTRIM(d.dxdesc1) AS dx_desc1,
    RTRIM(d.dxdesc2) AS dx_desc2,
    RTRIM(p.provis_dx) AS provisional,
    RTRIM(p.comment) AS comment,
    p.onset_date,
    p.stop_date,
    p.prob_stat_key AS status_key,
    p.log_datetime AS recorded_at,
    RTRIM(dr.lname) AS provider_last,
    RTRIM(dr.fname) AS provider_first,
    RTRIM(dr.title) AS provider_title
FROM conv.cac_pat_prob AS p
LEFT JOIN conv.dxmast AS d
    ON d.dxcode = p.dxcode
LEFT JOIN conv.drmast AS dr
    ON dr.drno = p.drno
WHERE p.patkey = :person_key
