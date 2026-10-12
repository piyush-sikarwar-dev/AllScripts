-- Newest non-cancelled visit date for the patients on the current page only.
SELECT
    e.IMREDEMEC_CODE AS emr_id,
    MAX(c.CON_START) AS last_visit
FROM HPSITE.ENCOUNTER AS e
JOIN HPSITE.CONTACT AS c
    ON c.IMREENC_CODE = e.IMREENC_CODE
WHERE e.IMREDEMEC_CODE IN :emr_ids
  AND ISNULL(c.CON_CANCELED, 0) = 0
GROUP BY e.IMREDEMEC_CODE
