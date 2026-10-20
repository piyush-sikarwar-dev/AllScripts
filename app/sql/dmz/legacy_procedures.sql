-- Pre-2010 records: the legacy patient's procedures (Procedures.PatientProcedures).
SELECT
    p.pat_treat_key AS procedure_id,
    RTRIM(p.proccode) AS code,
    RTRIM(m.insdesc1) AS desc1,
    RTRIM(m.insdesc2) AS desc2,
    RTRIM(m.stmtdesc) AS short_desc,
    p.date_of_service,
    p.stop_date,
    RTRIM(s.MEMR_Proc_Description) AS status,
    RTRIM(p.comment) AS comment,
    RTRIM(d.lname) AS provider_last,
    RTRIM(d.fname) AS provider_first,
    RTRIM(d.title) AS provider_title
FROM Procedures.PatientProcedures AS p
LEFT JOIN Procedures.ProceduresMaster AS m
    ON m.proccode = p.proccode
LEFT JOIN Procedures.ProcedureStatus AS s
    ON s.MEMR_Proc_Status = p.proc_status_key
LEFT JOIN conv.drmast AS d
    ON d.drno = p.drno
WHERE p.patkey = :person_key
