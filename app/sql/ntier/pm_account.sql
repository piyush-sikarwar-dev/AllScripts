-- Practice-management patient number and account number for one linked patient.
SELECT
    p.Patient_Number AS patient_number,
    a.Account_Number AS account_number
FROM PM.Patients AS p
LEFT JOIN PM.Accounts AS a
    ON a.Account_ID = p.Account_ID
WHERE p.Patient_ID = :ntier_id
