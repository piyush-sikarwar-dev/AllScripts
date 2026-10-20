-- Pre-2010 records: lab result values of the legacy patient (conv.cac_results reaches the patient
-- through Orders.LabTests and Orders.LabOrders).
SELECT
    r.sysresultno AS result_id,
    r.systestordered AS test_id,
    RTRIM(r.labresname) AS name,
    RTRIM(r.resultvalue) AS value,
    RTRIM(r.uom) AS units,
    RTRIM(r.reflow) AS ref_low,
    RTRIM(r.refhigh) AS ref_high,
    RTRIM(r.abnormalflags) AS flags,
    RTRIM(r.status) AS status,
    r.comments,
    r.sequence_num
FROM Orders.LabOrders AS o
JOIN Orders.LabTests AS t
    ON t.sysorderno = o.sysorderno
JOIN conv.cac_results AS r
    ON r.systestordered = t.systestorderno
WHERE o.patkey = :person_key
