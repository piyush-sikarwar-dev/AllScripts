-- Referrals the practice received for one PM patient: dates, status, authorization, visits
-- authorized, referred-from / referred-to practitioner and the insurance it was authorized under.
-- Never Practitioners.SSN / Federal_ID_No, Contacts.SSN or Carriers.Elig_Password.
SELECT
    r.Incoming_Referral_ID AS referral_id,
    r.Date_Of_Referral AS referral_date,
    r.Referral_Expiration_Date AS expires,
    r.Status AS status,
    r.Is_External_Referral AS is_external,
    r.Authorization_Number AS authorization_number,
    r.Pre_Certification_Number AS precert_number,
    r.Number_Authorized_Visits AS visits_authorized,
    r.Notes AS notes,
    pf.Last_Name AS from_last,
    pf.First_Name AS from_first,
    pf.Suffix AS from_suffix,
    pt.Last_Name AS to_last,
    pt.First_Name AS to_first,
    pt.Suffix AS to_suffix,
    c.Name AS carrier
FROM PM.Incoming_Referrals AS r
LEFT JOIN PM.Practitioners AS pf
    ON pf.Practitioner_ID = r.Referred_From_Practitioner_ID
LEFT JOIN PM.Practitioners AS pt
    ON pt.Practitioner_ID = r.Referred_To_Practitioner_ID
LEFT JOIN PM.Patient_Policies AS pp
    ON pp.Patient_Policy_ID = r.Patient_Policy_ID
LEFT JOIN PM.Policies AS po
    ON po.Policy_ID = pp.Policy_ID
LEFT JOIN PM.Carriers AS c
    ON c.Carrier_ID = po.Carrier_ID
WHERE r.Patient_ID = :ntier_id
