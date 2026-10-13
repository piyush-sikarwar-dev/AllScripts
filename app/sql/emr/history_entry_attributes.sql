-- Attributes of the patient's history entries, latest revision of each entry: allergy reactions,
-- family relationships, social history values (TITLE) and the attribute severity.
WITH attrs AS (
    SELECT
        a.HXDIAGNOSIS_ID,
        a.HXATTRIBUTE_ID,
        a.TITLE,
        a.ATTRIBUTEVALUE,
        a.SEVERITY_CODE,
        a.SORTORDER,
        DENSE_RANK() OVER (PARTITION BY a.HXDIAGNOSIS_ID ORDER BY a.TAG_REVISION DESC) AS rk
    FROM HPSITE.HXDIAGNOSIS_ATTRIBUTES AS a
    WHERE a.HXDIAGNOSIS_ID IN (
        SELECT h.HXDIAGNOSIS_ID FROM HPSITE.HX_DIAGNOSIS AS h WHERE h.PATIENT_ID = :emr_id
    )
)
SELECT
    HXDIAGNOSIS_ID AS hx_id,
    HXATTRIBUTE_ID AS attribute_id,
    TITLE AS title,
    ATTRIBUTEVALUE AS value,
    SEVERITY_CODE AS severity_code,
    SORTORDER AS sort_order
FROM attrs
WHERE rk = 1
