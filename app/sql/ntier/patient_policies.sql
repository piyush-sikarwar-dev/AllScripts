-- Practice-management insurance policies of one PM patient: coverage order, carrier, plan, group and
-- certificate numbers, dates and the policy holder's name. Never Contacts.SSN / Carriers.Elig_Password.
SELECT
    pp.Patient_Policy_ID AS policy_id,
    pp.Coverage AS coverage,
    pp.Relationship AS relationship,
    c.Name AS carrier,
    c.Phone AS carrier_phone,
    ip.Description AS plan_name,
    po.Group_Name AS group_name,
    po.Group_No AS group_number,
    po.Certificate_No AS certificate_number,
    po.Effective_Date AS effective_date,
    po.Expiration_Date AS expiration_date,
    ip.CoPayment_Amount AS copay,
    h.Last_Name AS holder_last,
    h.First_Name AS holder_first,
    h.Middle_Initial AS holder_middle,
    h.Date_Of_Birth AS holder_dob
FROM PM.Patient_Policies AS pp
JOIN PM.Policies AS po
    ON po.Policy_ID = pp.Policy_ID
LEFT JOIN PM.Carriers AS c
    ON c.Carrier_ID = po.Carrier_ID
LEFT JOIN PM.Insurance_Plans AS ip
    ON ip.Insurance_Plan_ID = po.Insurance_Plan_ID
LEFT JOIN PM.Contacts AS h
    ON h.Contact_ID = po.Contact_ID
WHERE pp.Patient_ID = :ntier_id
