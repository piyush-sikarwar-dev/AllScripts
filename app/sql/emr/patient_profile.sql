-- Patient details beyond the header: marital status, the guarantor (DEMGUARANTOR + home address;
-- never GUARANTOR_SSNUM) and whether a photo is on file.
SELECT
    d.DEM_MARITALSTATUS AS marital_status,
    d.DEM_PATREL_TOGUARANTOR AS guarantor_relation,
    g.GUARANTOR_LASTNAME AS guarantor_last,
    g.GUARANTOR_FIRSTNAME AS guarantor_first,
    g.GUARANTOR_MIDDLEINITIAL AS guarantor_middle,
    g.GUARANTOR_SUFFIX AS guarantor_suffix,
    g.GUARANTOR_DATEOFBIRTH AS guarantor_dob,
    ga.ADDR_ADDRESS AS guarantor_address,
    ga.ADDR_CITY AS guarantor_city,
    ga.ADDR_STATE AS guarantor_state,
    ga.ADDR_ZIP AS guarantor_zip,
    ga.ADDR_PHONE AS guarantor_phone,
    CASE WHEN EXISTS (SELECT 1 FROM HPSITE.DEMOGRAPHICPICTURE AS pic WHERE pic.IMREDEM_CODE = d.IMREDEM_CODE)
         THEN 1 ELSE 0 END AS has_photo
FROM HPSITE.DEMOGRAPHICS AS d
LEFT JOIN HPSITE.DEMGUARANTOR AS g
    ON g.GUARANTOR_CODE = d.GUARANTOR_CODE
LEFT JOIN HPSITE.ADDRESSES AS ga
    ON ga.IMREADDR_CODE = g.GUARANTOR_ADDRESS
WHERE d.IMREDEM_CODE = :emr_id
