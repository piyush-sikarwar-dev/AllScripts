-- Pre-2010 records: the tests ordered on the legacy patient's lab orders (name from Orders.Tests,
-- collected date and test comments from dbo.TestResultOrdertbl).
SELECT
    t.systestorderno AS test_id,
    t.sysorderno AS order_id,
    RTRIM(ts.testname) AS test_name,
    x.CollectedDate AS collected_date,
    x.testComments AS test_comments
FROM Orders.LabOrders AS o
JOIN Orders.LabTests AS t
    ON t.sysorderno = o.sysorderno
LEFT JOIN Orders.Tests AS ts
    ON ts.systestno = t.systestno
LEFT JOIN dbo.TestResultOrdertbl AS x
    ON x.systestorderno = t.systestorderno
WHERE o.patkey = :person_key
