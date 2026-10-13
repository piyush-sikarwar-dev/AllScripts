-- Notes tab index: every clinical document of the patient, metadata only (never the body), with
-- the clinician (HTML_DOCUMENTMAP source IMREPROV_CODE) and the patient's own encounter the
-- document belongs to (source IMREENC_CODE). AUTHOR is the application name, shown as "Source".
-- ATTACHED_FLAG = 1 rows are "Entire Chart Receipt" records with no image file: kept as notes.
SELECT
    d.DOCUMENT_ID AS document_id,
    d.CREATED_DATE AS created,
    d.TITLE AS title,
    d.AUTHOR AS app_source,
    d.STATUS AS status_code,
    enc.encounter_id,
    p.PROV_LASTNAME AS provider_last,
    p.PROV_FIRSTNAME AS provider_first,
    p.PROV_TITLE AS provider_title
FROM HPSITE.HTML_DOCUMENT_ORIG AS d
OUTER APPLY (
    SELECT TOP 1 e.IMREENC_CODE AS encounter_id
    FROM HPSITE.HTML_DOCUMENTMAP AS m
    JOIN HPSITE.ENCOUNTER AS e
        ON e.IMREENC_CODE = CASE
                WHEN m.SOURCE_CODE NOT LIKE '%[^0-9]%' AND LEN(m.SOURCE_CODE) BETWEEN 1 AND 9
                THEN CAST(m.SOURCE_CODE AS int)
            END
       AND e.IMREDEMEC_CODE = d.PATIENT_ID
    WHERE m.DOCUMENT_ID = d.DOCUMENT_ID
      AND m.SOURCE = 'IMREENC_CODE'
    ORDER BY m.MAP_ID
) AS enc
OUTER APPLY (
    SELECT TOP 1 CASE
            WHEN m.SOURCE_CODE NOT LIKE '%[^0-9]%' AND LEN(m.SOURCE_CODE) BETWEEN 1 AND 9
            THEN CAST(m.SOURCE_CODE AS int)
        END AS provider_code
    FROM HPSITE.HTML_DOCUMENTMAP AS m
    WHERE m.DOCUMENT_ID = d.DOCUMENT_ID
      AND m.SOURCE = 'IMREPROV_CODE'
    ORDER BY m.MAP_ID
) AS pm
LEFT JOIN HPSITE.PROVIDERS AS p
    ON p.IMREPROV_CODE = pm.provider_code
WHERE d.PATIENT_ID = :emr_id
