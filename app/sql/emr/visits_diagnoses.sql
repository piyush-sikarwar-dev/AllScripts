-- Assessed diagnoses (latest DX revision) for a list of encounters, for the visit list rows and
-- the visit detail. Grouped per encounter in Python (no STRING_AGG on this server).
SELECT
    ea.ENCOUNTER_ID AS encounter_id,
    ea.SORTORDER AS sort_order,
    d.code AS code,
    d.title AS title
FROM HPSITE.ENCOUNTER_ASSESSMENT AS ea
CROSS APPLY (
        SELECT TOP 1
            x.DX_CODE AS code,
            COALESCE(NULLIF(LTRIM(RTRIM(x.DX_TITLE)), ''), x.DX_DESCRIPTION) AS title
        FROM HPSITE.DX AS x
        WHERE x.IMREDX_CODE = ea.DX_ID
        ORDER BY x.TAG_REVISION DESC
    ) AS d
WHERE ea.ENCOUNTER_ID IN :encounter_ids
