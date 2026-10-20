-- Pre-2010 records: the legacy patient's preferred, area and mail-order pharmacies.
SELECT
    k.kind,
    RTRIM(m.pharmname) AS name,
    RTRIM(m.street1) AS street1,
    RTRIM(m.street2) AS street2,
    RTRIM(m.city) AS city,
    RTRIM(m.state) AS state,
    RTRIM(m.zipcode) AS zip,
    RTRIM(m.areacd1) AS phone_area,
    RTRIM(m.phone1) AS phone,
    RTRIM(m.areacdfax) AS fax_area,
    RTRIM(m.phonefax) AS fax
FROM conv.cac_pat_pharm_pref AS p
CROSS APPLY (
    SELECT 'preferred' AS kind, p.pharmidkey AS pharmid
    UNION ALL SELECT 'area', p.pharmid_area
    UNION ALL SELECT 'mail order', p.pharmid_mailord
) AS k
JOIN conv.pharmmast AS m
    ON m.pharmid = k.pharmid
WHERE p.patkey = :person_key
