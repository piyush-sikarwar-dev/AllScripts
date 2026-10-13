-- Visits tab list (Option C): one row per ENCOUNTER with at least one non-cancelled CONTACT,
-- newest first, one page (25). Filters: visit-type category, year, and a search text matching
-- the provider name or any assessed diagnosis title/code (latest DX revision).
-- LIKE uses '!' as escape character (a backslash confuses the ODBC parameter parser).
-- Never write parameter names with a leading colon in comments: they become bind parameters.
-- LIKE uses '!' as escape character: a backslash escape confuses the ODBC parameter parser.
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
),
v AS (
    SELECT
        enc.encounter_id,
        enc.visit_type_code,
        enc.signed,
        enc.visit_date,
        p.PROV_LASTNAME AS provider_last,
        p.PROV_FIRSTNAME AS provider_first,
        p.PROV_TITLE AS provider_title,
        l.LOCATION_NAME AS location
    FROM enc
    LEFT JOIN HPSITE.PROVIDERS AS p
        ON p.IMREPROV_CODE = enc.provider_code
    LEFT JOIN HPSITE.LOCATION AS l
        ON l.LOCATION_ID = enc.location_id
    WHERE (:year IS NULL OR YEAR(enc.visit_date) = :year)
      AND (
            :q_like IS NULL
            OR p.PROV_LASTNAME LIKE :q_like ESCAPE '!'
            OR p.PROV_FIRSTNAME LIKE :q_like ESCAPE '!'
            OR EXISTS (
                SELECT 1
                FROM HPSITE.ENCOUNTER_ASSESSMENT AS ea
                CROSS APPLY (
        SELECT TOP 1
            x.DX_CODE AS code,
            COALESCE(NULLIF(LTRIM(RTRIM(x.DX_TITLE)), ''), x.DX_DESCRIPTION) AS title
        FROM HPSITE.DX AS x
        WHERE x.IMREDX_CODE = ea.DX_ID
        ORDER BY x.TAG_REVISION DESC
    ) AS d
                WHERE ea.ENCOUNTER_ID = enc.encounter_id
                  AND (d.title LIKE :q_like ESCAPE '!' OR d.code LIKE :q_like ESCAPE '!')
            )
      )
)
SELECT
    v.encounter_id,
    v.visit_type_code,
    v.signed,
    v.visit_date,
    v.provider_last,
    v.provider_first,
    v.provider_title,
    v.location,
    COUNT(1) OVER () AS total_count
FROM v
ORDER BY v.visit_date DESC, v.encounter_id DESC
OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
OPTION (RECOMPILE)
