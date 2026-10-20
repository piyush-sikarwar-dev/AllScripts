-- Lab orders of one patient with their own completion status (ORDCOMP: 1 Ordered, 2 Preliminary,
-- 3 Final, 4 Reviewed, 5 Pending, 6 Canceled, 7 Erroneous), ordering provider and the diagnosis
-- given for the order (latest DX revision). Never PROV_PASSWORD / PROV_SSNUM.
SELECT
    o.IMRELABORDER_CODE AS order_id,
    o.LABORDER_ORDERDATE AS ordered_at,
    o.LABORDER_NAME AS test,
    c.LABCAT_LONGNAME AS catalog_name,
    o.LABORDER_COMPLETIONSTATUS AS status_code,
    o.REPORT_DATE AS reported_at,
    o.LABORDER_COMMENT AS comment,
    o.INHOUSE_FLAG AS in_house,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title,
    dx.DX_TITLE AS diagnosis,
    dx.DX_CODE AS diagnosis_code
FROM HPSITE.LABORDERS AS o
LEFT JOIN HPSITE.LABCATALOG AS c
    ON c.IMRELABCAT_CODE = o.IMRELABCAT_CODE
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = o.IMREPROV_CODE
OUTER APPLY (
    SELECT TOP 1 d.DX_TITLE, d.DX_CODE
    FROM HPSITE.DX AS d
    WHERE d.IMREDX_CODE = o.IMREDX_CODE
    ORDER BY d.TAG_REVISION DESC
) AS dx
WHERE o.IMREDEMEC_CODE = :emr_id
