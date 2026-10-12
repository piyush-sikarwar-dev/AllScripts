-- Names / DOB for a list of patients (release log page). Explicit columns; never DEM_SSNUM.
SELECT
    d.IMREDEM_CODE AS emr_id,
    d.DEM_LASTNAME AS last_name,
    d.DEM_FIRSTNAME AS first_name,
    d.DEM_MIDDLEINITIAL AS middle_initial
FROM HPSITE.DEMOGRAPHICS AS d
WHERE d.IMREDEM_CODE IN :emr_ids
