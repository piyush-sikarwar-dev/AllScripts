-- Consents of one patient (CONSENT dictionary, answers CONANS).
SELECT
    c.CONSENT_ID AS consent_id,
    c.CONSENT_CODE AS consent_code,
    c.ANSWER_CODE AS answer_code,
    c.EXPIRATION_DATE AS expires,
    c.TAG_SYSTEMDATE AS recorded_at
FROM HPSITE.PATIENT_CONSENT AS c
WHERE c.PATIENT_ID = :emr_id
