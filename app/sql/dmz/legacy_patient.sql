-- Pre-2010 records: one legacy patient's header (DMZ conv.person). ssno is never selected.
SELECT
    p.personkey AS person_key,
    RTRIM(p.lname) AS last_name,
    RTRIM(p.fname) AS first_name,
    RTRIM(p.mi) AS middle_initial,
    RTRIM(p.suffix) AS suffix,
    p.birthdate AS dob,
    RTRIM(p.sex) AS sex,
    p.deceased AS deceased,
    RTRIM(p.street1) AS street1,
    RTRIM(p.street2) AS street2,
    RTRIM(p.city) AS city,
    RTRIM(p.state) AS state,
    RTRIM(p.zip) AS zip,
    RTRIM(p.harea) AS home_area,
    RTRIM(p.hphone) AS home_phone,
    RTRIM(p.patid) AS legacy_id
FROM conv.person AS p
WHERE p.personkey = :person_key
