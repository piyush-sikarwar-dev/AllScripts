-- Assigned providers of one patient (PHYSICIANROLE dictionary). Never PROV_PASSWORD / PROV_SSNUM.
SELECT
    pp.PHYSICIAN_ROLE_CODE AS role_code,
    pp.ADDED_DATE AS added_at,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM HPSITE.PATIENT_PHYSICIANS AS pp
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = pp.PROVIDER_ID
WHERE pp.PATIENT_ID = :emr_id
