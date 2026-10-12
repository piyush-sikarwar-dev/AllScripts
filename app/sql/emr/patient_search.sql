-- One page of patients (25) for the dashboard, merged-away records excluded.
-- Name filters arrive pre-escaped with a trailing % (LIKE ... ESCAPE '\').
SELECT
    d.IMREDEM_CODE AS emr_id,
    d.DEM_LASTNAME AS last_name,
    d.DEM_FIRSTNAME AS first_name,
    d.DEM_MIDDLEINITIAL AS middle_initial,
    d.DEM_DATEOFBIRTH AS dob,
    d.DEM_DATEOFBIRTHMASK AS dob_mask,
    d.DEM_SEX AS sex_code,
    d.DEM_DECEASED AS deceased,
    COUNT(*) OVER () AS total_count
FROM HPSITE.DEMOGRAPHICS AS d
WHERE NOT EXISTS (
        SELECT 1
        FROM HPSITE.PATIENT_MERGE_HISTORY AS h
        WHERE h.ORIGINAL_DEM_CODE = d.IMREDEM_CODE
          AND h.CURRENT_DEM_CODE <> d.IMREDEM_CODE
    )
  AND (:last_name_like IS NULL OR d.DEM_LASTNAME LIKE :last_name_like ESCAPE '\')
  AND (:first_name_like IS NULL OR d.DEM_FIRSTNAME LIKE :first_name_like ESCAPE '\')
  AND (:dob IS NULL OR CAST(d.DEM_DATEOFBIRTH AS date) = :dob)
  AND (:chart_id IS NULL OR EXISTS (
        SELECT 1
        FROM HPSITE.PATIENT_IDENTIFIER AS pi2
        WHERE pi2.PATIENT_ID = d.IMREDEM_CODE
          AND LTRIM(RTRIM(pi2.IDENTIFIER_VALUE)) = :chart_id
    ))
ORDER BY d.DEM_LASTNAME, d.DEM_FIRSTNAME, d.IMREDEM_CODE
OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
OPTION (RECOMPILE)
