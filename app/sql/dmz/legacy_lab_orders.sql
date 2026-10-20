-- Pre-2010 records: the legacy patient's lab orders with their dates (dbo.Resultsmigratetbl holds
-- the order / service / result dates, one row per order), ordering provider and facility.
SELECT
    o.sysorderno AS order_id,
    RTRIM(o.orderno) AS order_no,
    m.orderdate AS order_date,
    m.servicedate AS service_date,
    m.resdate AS result_date,
    RTRIM(o.comments) AS comments,
    RTRIM(d.lname) AS provider_last,
    RTRIM(d.fname) AS provider_first,
    RTRIM(d.title) AS provider_title,
    RTRIM(f.facname) AS facility
FROM Orders.LabOrders AS o
LEFT JOIN dbo.Resultsmigratetbl AS m
    ON m.sysorderno = o.sysorderno
LEFT JOIN conv.drmast AS d
    ON d.drno = o.drordering
LEFT JOIN conv.facmast AS f
    ON f.faccode = o.faccode
WHERE o.patkey = :person_key
