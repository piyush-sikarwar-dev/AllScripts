-- Pre-2010 records: one legacy patient's header and demographics (DMZ conv.person), with the primary
-- provider and office from conv.patgroup (one row per patient) and whether a photo is on file.
-- ssno is never selected.
SELECT
    p.personkey AS person_key,
    RTRIM(p.lname) AS last_name,
    RTRIM(p.fname) AS first_name,
    RTRIM(p.mi) AS middle_initial,
    RTRIM(p.suffix) AS suffix,
    RTRIM(p.alias) AS alias,
    p.birthdate AS dob,
    RTRIM(p.sex) AS sex,
    RTRIM(p.marstat) AS marital_status,
    RTRIM(p.race) AS race,
    p.deceased AS deceased,
    RTRIM(p.street1) AS street1,
    RTRIM(p.street2) AS street2,
    RTRIM(p.street3) AS street3,
    RTRIM(p.city) AS city,
    RTRIM(p.state) AS state,
    RTRIM(p.zip) AS zip,
    RTRIM(p.harea) AS home_area,
    RTRIM(p.hphone) AS home_phone,
    RTRIM(p.warea) AS work_area,
    RTRIM(p.wphone) AS work_phone,
    RTRIM(p.wext) AS work_ext,
    RTRIM(p.email) AS email,
    RTRIM(p.patid) AS legacy_id,
    RTRIM(p.pattype) AS patient_type,
    p.entrydate AS chart_created,
    RTRIM(d.lname) AS provider_last,
    RTRIM(d.fname) AS provider_first,
    RTRIM(d.title) AS provider_title,
    RTRIM(f.facname) AS office,
    CASE WHEN EXISTS (SELECT 1 FROM conv.cac_pat_photo AS ph WHERE ph.patkey = p.personkey)
         THEN 1 ELSE 0 END AS has_photo
FROM conv.person AS p
LEFT JOIN conv.patgroup AS g
    ON g.patkey = p.personkey
LEFT JOIN conv.drmast AS d
    ON d.drno = g.drno
LEFT JOIN conv.facmast AS f
    ON f.faccode = g.faccode
WHERE p.personkey = :person_key
