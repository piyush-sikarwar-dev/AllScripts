-- Release-of-information requests recorded in Allscripts before it was retired (659 rows; read whole
-- for the Release log page). Requester name only (no address / phone / fax).
SELECT
    q.REQUESTID AS request_id,
    q.PATIENTID AS emr_id,
    q.STATUS AS status,
    s.STATUSTEXT AS status_text,
    q.APPROVALSTATUS AS approval,
    a.STATUSTEXT AS approval_text,
    q.ENTRYDATE AS entered_at,
    q.DELIVERBYDATE AS deliver_by,
    q.COMPLETEDATE AS completed_at,
    q.ENTIRECHARTFLAG AS entire_chart,
    q.FORPATIENTFLAG AS for_patient,
    q.HIGHPRIORITYFLAG AS high_priority,
    q.REQUESTERNAME AS requester,
    p.PROV_LASTNAME AS entered_last,
    p.PROV_FIRSTNAME AS entered_first
FROM HPSITE.PHIREQUEST AS q
LEFT JOIN HPSITE.PHIREQUEST_STATUS AS s
    ON s.STATUSID = q.STATUS
LEFT JOIN HPSITE.PHIREQUEST_APPROVALSTATUS AS a
    ON a.STATUSID = q.APPROVALSTATUS
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = q.ENTRYPROVID
