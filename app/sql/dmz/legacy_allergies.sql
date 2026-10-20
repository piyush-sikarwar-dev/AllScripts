-- Pre-2010 records: the legacy patient's allergies with allergen, category, status and severity
-- (severity labels live in conv.cac_control_values, control_id 27).
SELECT
    a.pat_alrg_key AS allergy_id,
    RTRIM(c.name) AS allergen,
    RTRIM(c.description) AS allergen_desc,
    RTRIM(cat.name) AS category,
    a.alrg_stat_key AS status_key,
    RTRIM(st.name) AS status,
    RTRIM(a.active_flag) AS active_flag,
    RTRIM(sev.display_text) AS severity,
    RTRIM(a.comment) AS comment,
    a.date_of_service AS noted_date,
    RTRIM(dr.lname) AS provider_last,
    RTRIM(dr.fname) AS provider_first,
    RTRIM(dr.title) AS provider_title
FROM conv.cac_pat_alrg AS a
LEFT JOIN conv.cac_alrg_code AS c
    ON c.alrg_code_key = a.alrg_code_key
LEFT JOIN conv.cac_alrg_cat AS cat
    ON cat.alrg_cat_key = a.alrg_cat_key
LEFT JOIN conv.cac_alrg_status AS st
    ON st.alrg_stat_key = a.alrg_stat_key
LEFT JOIN conv.cac_control_values AS sev
    ON sev.lookup_key = a.severity_key
LEFT JOIN conv.drmast AS dr
    ON dr.drno = a.drno
WHERE a.patkey = :person_key
