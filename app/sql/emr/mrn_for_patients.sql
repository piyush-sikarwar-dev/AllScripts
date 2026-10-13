-- MRN for the patients on the current page: HPSITE.PATIENT_IDENTIFIER, preferred value first,
-- then the lowest PIDSOURCE_ID (2 = "PM 1", 3 = "Allscripts Professional PM"), then the lowest record.
SELECT x.emr_id, x.mrn
FROM (
    SELECT
        pi.PATIENT_ID AS emr_id,
        LTRIM(RTRIM(pi.IDENTIFIER_VALUE)) AS mrn,
        ROW_NUMBER() OVER (
            PARTITION BY pi.PATIENT_ID
            ORDER BY pi.PREFERRED DESC, pi.PIDSOURCE_ID, pi.PATIENT_IDENTIFIER_ID
        ) AS rn
    FROM HPSITE.PATIENT_IDENTIFIER AS pi
    WHERE pi.PATIENT_ID IN :emr_ids
      AND LEN(LTRIM(RTRIM(pi.IDENTIFIER_VALUE))) > 0
) AS x
WHERE x.rn = 1
