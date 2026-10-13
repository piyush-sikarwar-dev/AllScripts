-- Activity summary (visit-type filter applies, all years): total visits, last visit, most seen
-- provider and most frequent diagnosis (latest DX revision); ties go to the most recent.
WITH enc0 AS (
    SELECT
        e.IMREENC_CODE AS encounter_id,
        e.ENC_VISITTYPE AS visit_type_code,
        e.ENC_SIGNED AS signed,
        e.IMREPROV_CODE AS enc_provider,
        e.LOCATION_ID AS location_id,
        MIN(c.CON_START) AS visit_date
    FROM HPSITE.ENCOUNTER AS e
    JOIN HPSITE.CONTACT AS c
        ON c.IMREENC_CODE = e.IMREENC_CODE
       AND ISNULL(c.CON_CANCELED, 0) = 0
    WHERE e.IMREDEMEC_CODE = :emr_id
      AND (:all_types = 1 OR e.ENC_VISITTYPE IN :visit_type_codes)
    GROUP BY e.IMREENC_CODE, e.ENC_VISITTYPE, e.ENC_SIGNED, e.IMREPROV_CODE, e.LOCATION_ID
),
enc AS (
    SELECT
        enc0.encounter_id,
        enc0.visit_type_code,
        enc0.signed,
        enc0.location_id,
        enc0.visit_date,
        COALESCE(enc0.enc_provider, fc.IMREPROV_CODE) AS provider_code
    FROM enc0
    OUTER APPLY (
        SELECT TOP 1 c2.IMREPROV_CODE
        FROM HPSITE.CONTACT AS c2
        WHERE c2.IMREENC_CODE = enc0.encounter_id
          AND ISNULL(c2.CON_CANCELED, 0) = 0
          AND c2.IMREPROV_CODE IS NOT NULL
        ORDER BY c2.CON_START
    ) AS fc
)
SELECT
    (SELECT COUNT(1) FROM enc) AS total,
    (SELECT MAX(enc.visit_date) FROM enc) AS last_visit,
    tp.provider_last,
    tp.provider_first,
    tp.provider_title,
    tp.provider_count,
    td.dx_code,
    td.dx_title,
    td.dx_count
FROM (SELECT 1 AS one) AS base
OUTER APPLY (
    SELECT TOP 1
        p.PROV_LASTNAME AS provider_last,
        p.PROV_FIRSTNAME AS provider_first,
        p.PROV_TITLE AS provider_title,
        COUNT(1) AS provider_count
    FROM enc
    JOIN HPSITE.PROVIDERS AS p
        ON p.IMREPROV_CODE = enc.provider_code
    GROUP BY p.IMREPROV_CODE, p.PROV_LASTNAME, p.PROV_FIRSTNAME, p.PROV_TITLE
    ORDER BY COUNT(1) DESC, MAX(enc.visit_date) DESC
) AS tp
OUTER APPLY (
    SELECT TOP 1
        d.code AS dx_code,
        d.title AS dx_title,
        COUNT(DISTINCT enc.encounter_id) AS dx_count
    FROM enc
    JOIN HPSITE.ENCOUNTER_ASSESSMENT AS ea
        ON ea.ENCOUNTER_ID = enc.encounter_id
    CROSS APPLY (
        SELECT TOP 1
            x.DX_CODE AS code,
            COALESCE(NULLIF(LTRIM(RTRIM(x.DX_TITLE)), ''), x.DX_DESCRIPTION) AS title
        FROM HPSITE.DX AS x
        WHERE x.IMREDX_CODE = ea.DX_ID
        ORDER BY x.TAG_REVISION DESC
    ) AS d
    GROUP BY d.code, d.title
    ORDER BY COUNT(DISTINCT enc.encounter_id) DESC, MAX(enc.visit_date) DESC
) AS td
