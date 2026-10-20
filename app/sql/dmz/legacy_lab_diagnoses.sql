-- Pre-2010 records: diagnoses (ICD-9) given for the legacy patient's ordered tests.
SELECT
    l.systestorderno AS test_id,
    RTRIM(l.dxcode) AS dx_code,
    RTRIM(d.dxdesc1) AS dx_desc,
    l.dxpriority AS priority
FROM Orders.LabOrders AS o
JOIN Orders.LabTests AS t
    ON t.sysorderno = o.sysorderno
JOIN conv.cac_diaglink AS l
    ON l.systestorderno = t.systestorderno
LEFT JOIN conv.dxmast AS d
    ON d.dxcode = l.dxcode
WHERE o.patkey = :person_key
