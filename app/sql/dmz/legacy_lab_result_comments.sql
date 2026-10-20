-- Pre-2010 records: comment lines attached to the legacy patient's lab results (conv.cac_rescom).
SELECT
    c.sysresultno AS result_id,
    c.resultno AS line_no,
    c.comments AS comment
FROM Orders.LabOrders AS o
JOIN Orders.LabTests AS t
    ON t.sysorderno = o.sysorderno
JOIN conv.cac_results AS r
    ON r.systestordered = t.systestorderno
JOIN conv.cac_rescom AS c
    ON c.sysresultno = r.sysresultno
WHERE o.patkey = :person_key
