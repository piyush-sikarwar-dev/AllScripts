-- Race codes of one patient (RACE-SUMMARY dictionary).
SELECT r.RACE_CODE AS code
FROM HPSITE.PATIENT_RACE AS r
WHERE r.PATIENT_ID = :emr_id
