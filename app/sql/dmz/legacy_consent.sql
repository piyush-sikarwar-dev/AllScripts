-- Pre-2010 records: the legacy patient's consent flags (Patient.Consent).
SELECT
    RTRIM(c.general_consent) AS general_consent,
    RTRIM(c.demo_consent) AS demographics_consent,
    RTRIM(c.ins_consent) AS insurance_consent,
    RTRIM(c.medhx_consent) AS medical_history_consent
FROM Patient.Consent AS c
WHERE c.patkey = :person_key
