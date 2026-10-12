-- Attribute rows (e.g. allergy reactions) for a patient's history items, latest revision of each.
WITH attrs AS (
    SELECT
        a.HXDIAGNOSIS_ID,
        a.TITLE,
        a.SORTORDER,
        DENSE_RANK() OVER (PARTITION BY a.HXDIAGNOSIS_ID ORDER BY a.TAG_REVISION DESC) AS rk
    FROM HPSITE.HXDIAGNOSIS_ATTRIBUTES AS a
    JOIN HPSITE.HX_DIAGNOSIS AS h
        ON h.HXDIAGNOSIS_ID = a.HXDIAGNOSIS_ID
    WHERE h.PATIENT_ID = :emr_id
      AND h.CATEGORY_CODE IN :category_codes
)
SELECT DISTINCT
    HXDIAGNOSIS_ID AS hx_id,
    TITLE AS title,
    SORTORDER AS sort_order
FROM attrs
WHERE rk = 1
