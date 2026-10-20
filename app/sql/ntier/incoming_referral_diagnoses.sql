-- Diagnoses given on the referrals one PM patient received.
SELECT
    d.Incoming_Referral_ID AS referral_id,
    dc.Diagnosis_Code AS code,
    dc.Description AS description
FROM PM.Incoming_Referrals AS r
JOIN PM.Incoming_Referral_Diags AS d
    ON d.Incoming_Referral_ID = r.Incoming_Referral_ID
LEFT JOIN PM.Diagnosis_Codes AS dc
    ON dc.Diagnosis_Code_ID = d.Diagnosis_Code_ID
WHERE r.Patient_ID = :ntier_id
