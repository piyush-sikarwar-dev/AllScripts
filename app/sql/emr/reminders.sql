-- Clinical reminders of one patient (REM_PRIORITY uses the MSGPRIOR dictionary). Never
-- PROV_PASSWORD / PROV_SSNUM.
SELECT
    r.IMREREMINDER_CODE AS reminder_id,
    r.REM_DATE AS due_at,
    r.REM_SUBJECT AS subject,
    r.REM_PRIORITY AS priority,
    r.REM_COMPLETEDFLAG AS completed,
    r.REM_DATECOMPLETED AS completed_at,
    r.REM_ENTEREDDATE AS entered_at,
    r.REM_ERRONEOUS AS erroneous,
    pe.PROV_LASTNAME AS entered_last,
    pe.PROV_FIRSTNAME AS entered_first,
    pc.PROV_LASTNAME AS completed_last,
    pc.PROV_FIRSTNAME AS completed_first
FROM HPSITE.REMINDERS AS r
LEFT JOIN HPSITE.PROVIDERS AS pe
    ON pe.IMREPROV_CODE = r.REM_ENTEREDBYPROV
LEFT JOIN HPSITE.PROVIDERS AS pc
    ON pc.IMREPROV_CODE = r.REM_COMPLETEDBYPROV
WHERE r.IMREDEMEC_CODE = :emr_id
