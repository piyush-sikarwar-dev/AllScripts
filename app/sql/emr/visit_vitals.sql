-- Vital signs of one visit (contact), only if it belongs to the patient; erroneous readings
-- excluded. Uses the IMRECONTACT_CODE + IMREDEM_CODE index (docs/PERFORMANCE_PLAN.md #4).
SELECT
    v.VITALS_CODE AS vital_id,
    v.IMRECONTACT_CODE AS contact_id,
    v.VITAL_DATETIME AS taken,
    v.VITAL_BP_SYSTOLIC AS systolic,
    v.VITAL_BP_DIASTOLIC AS diastolic,
    v.VITAL_PULSE AS pulse,
    v.VITAL_TEMPERATURE AS temperature,
    v.VITAL_TEMPERATURE_UNIT_CODE AS temperature_unit,
    v.VITAL_WEIGHT AS weight,
    v.VITAL_WEIGHT_UNIT_CODE AS weight_unit,
    v.VITAL_HEIGHT AS height,
    v.VITAL_HEIGHT_UNIT_CODE AS height_unit,
    v.VITAL_PULSE_OX AS spo2,
    v.VITAL_PAIN_LEVEL AS pain
FROM HPSITE.VITALS_DATA AS v
WHERE v.IMRECONTACT_CODE = :contact_id
  AND v.IMREDEM_CODE = :emr_id
  AND ISNULL(v.VITAL_ERRONEOUS_IND, 0) = 0
