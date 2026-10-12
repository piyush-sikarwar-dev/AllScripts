-- Diagnoses assessed at an encounter, at the DX revision recorded with the assessment.
SELECT
    a.SORTORDER AS sort_order,
    d.DX_TITLE AS title,
    d.DX_CODE AS code,
    d.DX_SOURCE AS code_system
FROM HPSITE.ENCOUNTER_ASSESSMENT AS a
JOIN HPSITE.DX AS d
    ON d.IMREDX_CODE = a.DX_ID
   AND d.TAG_REVISION = a.DX_REVISION
WHERE a.ENCOUNTER_ID = :encounter_id
