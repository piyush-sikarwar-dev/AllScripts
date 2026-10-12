-- Merged-away EMR patients and the record they were merged into.
SELECT
    h.ORIGINAL_DEM_CODE AS original_id,
    h.CURRENT_DEM_CODE AS current_id
FROM HPSITE.PATIENT_MERGE_HISTORY AS h
WHERE h.ORIGINAL_DEM_CODE <> h.CURRENT_DEM_CODE
