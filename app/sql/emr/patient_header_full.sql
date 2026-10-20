-- Chart header in one round trip (docs/PERFORMANCE_PLAN.md #5): demographics + home address +
-- primary insurance (lowest INS_RANK, not archived) + MRN (preferred, then lowest PIDSOURCE_ID,
-- then lowest identifier record). Explicit columns; never DEM_SSNUM or INS_SUBSSNUM.
SELECT
    d.IMREDEM_CODE AS emr_id,
    d.DEM_LASTNAME AS last_name,
    d.DEM_FIRSTNAME AS first_name,
    d.DEM_MIDDLEINITIAL AS middle_initial,
    d.DEM_DATEOFBIRTH AS dob,
    d.DEM_DATEOFBIRTHMASK AS dob_mask,
    d.DEM_SEX AS sex_code,
    d.DEM_DECEASED AS deceased,
    d.DEM_DATEOFDEATH AS date_of_death,
    d.DEM_DATEOFDEATHMASK AS date_of_death_mask,
    a.ADDR_ADDRESS AS address,
    a.ADDR_CITY AS city,
    a.ADDR_STATE AS state,
    a.ADDR_ZIP AS zip,
    a.ADDR_PHONE AS phone,
    ins.carrier_name AS primary_insurance,
    m.mrn AS mrn,
    CASE WHEN EXISTS (SELECT 1 FROM HPSITE.DEMOGRAPHICPICTURE AS pic WHERE pic.IMREDEM_CODE = d.IMREDEM_CODE)
         THEN 1 ELSE 0 END AS has_photo
FROM HPSITE.DEMOGRAPHICS AS d
LEFT JOIN HPSITE.ADDRESSES AS a
    ON a.IMREADDR_CODE = d.DEM_HOMEADDR
OUTER APPLY (
    SELECT TOP 1 c.CARRIER_NAME AS carrier_name
    FROM HPSITE.INSURANCES AS i
    LEFT JOIN HPSITE.INSURANCECARRIERS AS c
        ON c.IMRECARRIER_CODE = i.IMRECARRIER_CODE
    WHERE i.IMREDEM_CODE = d.IMREDEM_CODE
      AND ISNULL(i.TAG_ARCHIVED, 0) = 0
    ORDER BY i.INS_RANK, i.IMREINS_CODE
) AS ins
OUTER APPLY (
    SELECT TOP 1 LTRIM(RTRIM(pi.IDENTIFIER_VALUE)) AS mrn
    FROM HPSITE.PATIENT_IDENTIFIER AS pi
    WHERE pi.PATIENT_ID = d.IMREDEM_CODE
      AND LEN(LTRIM(RTRIM(pi.IDENTIFIER_VALUE))) > 0
    ORDER BY pi.PREFERRED DESC, pi.PIDSOURCE_ID, pi.PATIENT_IDENTIFIER_ID
) AS m
WHERE d.IMREDEM_CODE = :emr_id
