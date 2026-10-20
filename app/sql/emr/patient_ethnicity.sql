-- Ethnicity codes of one patient (ETHNICITY-SUM dictionary).
SELECT e.ETHNICITY_CODE AS code
FROM HPSITE.PATIENT_ETHNICITY AS e
WHERE e.PATIENT_ID = :emr_id
