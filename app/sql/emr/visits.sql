-- All non-cancelled contacts (visits and other chart entries) for one patient.
-- The "real visits only" filter is applied in the app from config/visit_types.yaml.
SELECT
    c.IMRECONTACT_CODE AS contact_id,
    e.IMREENC_CODE AS encounter_id,
    c.CON_START AS start,
    e.ENC_VISITTYPE AS visit_type_code,
    e.ENC_SIGNED AS signed,
    e.ENC_DIAGNOSES AS diagnoses,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title,
    l.LOCATION_NAME AS location
FROM HPSITE.ENCOUNTER AS e
JOIN HPSITE.CONTACT AS c
    ON c.IMREENC_CODE = e.IMREENC_CODE
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = COALESCE(c.IMREPROV_CODE, e.IMREPROV_CODE)
LEFT JOIN HPSITE.LOCATION AS l
    ON l.LOCATION_ID = e.LOCATION_ID
WHERE e.IMREDEMEC_CODE = :emr_id
  AND ISNULL(c.CON_CANCELED, 0) = 0
