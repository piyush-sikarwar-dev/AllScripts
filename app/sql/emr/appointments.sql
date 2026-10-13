-- Appointments tab: the patient's EMR schedule (HPSITE.ARCH_SCHEDULE is the EMR appointment table
-- despite the ARCH_ prefix, CLAUDE.md rule 4). SCHED_TEXT is not selected: it holds free text such
-- as patient names. SCHED_PMSID links to Ntier PM.Appointments (2014 onwards).
SELECT
    s.IMRESCHED_CODE AS sched_id,
    s.SCHED_DATE AS starts,
    s.SCHED_STATUS AS status_code,
    s.SCHED_PMSID AS pm_id,
    s.SCHED_TIMEIN AS time_in,
    s.SCHED_TIMEOUT AS time_out,
    s.SCHED_COMMENT AS comment,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title,
    l.LOCATION_NAME AS location
FROM HPSITE.ARCH_SCHEDULE AS s
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = s.IMREPROV_CODE
LEFT JOIN HPSITE.LOCATION AS l
    ON l.LOCATION_ID = s.LOCATION_ID
WHERE s.IMREDEM_CODE = :emr_id
