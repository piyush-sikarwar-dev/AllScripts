-- Chart header: demographics + home address. Explicit columns; never DEM_SSNUM.
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
    a.ADDR_PHONE AS phone
FROM HPSITE.DEMOGRAPHICS AS d
LEFT JOIN HPSITE.ADDRESSES AS a
    ON a.IMREADDR_CODE = d.DEM_HOMEADDR
WHERE d.IMREDEM_CODE = :emr_id
