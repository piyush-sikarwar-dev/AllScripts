-- One visit (encounter) header, only if it belongs to the patient and has a non-cancelled contact.
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
      AND e.IMREENC_CODE = :encounter_id
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
