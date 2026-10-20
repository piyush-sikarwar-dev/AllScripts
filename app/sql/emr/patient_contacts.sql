-- Emergency contacts and health-care proxies of one patient, with their address and phones.
SELECT
    pc.PATCON_CODE AS contact_id,
    pc.PATCON_RANK AS rank,
    pc.PATCON_LASTNAME AS last_name,
    pc.PATCON_FIRSTNAME AS first_name,
    pc.PATCON_MIDDLENAME AS middle_name,
    pc.PATCON_RELATIONSHIP AS relationship,
    pc.PATCON_EMERGENCY AS emergency,
    pc.PATCON_HEALTHCAREPROXY AS proxy,
    a.ADDR_ADDRESS AS address,
    a.ADDR_CITY AS city,
    a.ADDR_STATE AS state,
    a.ADDR_ZIP AS zip,
    a.ADDR_PHONE AS phone,
    a.ADDR_CARPHONE AS mobile,
    a.ADDR_EMAILADDRESS AS email
FROM HPSITE.PATIENT_CONTACTS AS pc
LEFT JOIN HPSITE.ADDRESSES AS a
    ON a.IMREADDR_CODE = pc.PATCON_ADDRESS
WHERE pc.IMREDEM_CODE = :emr_id
