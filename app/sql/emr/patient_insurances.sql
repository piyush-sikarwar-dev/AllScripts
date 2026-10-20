-- All insurance policies of one patient (archived ones included; the service hides them unless
-- "show archived" is on). Subscriber name / DOB / relationship; never INS_SUBSSNUM.
SELECT
    i.IMREINS_CODE AS policy_id,
    i.INS_RANK AS rank,
    c.CARRIER_NAME AS carrier,
    ca.ADDR_PHONE AS carrier_phone,
    i.INS_PLANTYPE AS plan_type,
    i.INS_GROUPNUMBER AS group_number,
    i.INS_PLANNUMBER AS plan_number,
    i.INS_ENROLLMENTID AS member_id,
    i.INS_ENROLLMENTDATE AS effective_date,
    i.INS_TERMINATIONDATE AS termination_date,
    i.INS_SUBLASTNAME AS subscriber_last,
    i.INS_SUBFIRSTNAME AS subscriber_first,
    i.INS_SUBMIDDLEINITIAL AS subscriber_middle,
    i.INS_SUBDATEOFBIRTH AS subscriber_dob,
    i.INS_PATREL_TOSUB AS relation_code,
    i.INS_WC_FLAG AS workers_comp,
    i.TAG_ARCHIVED AS archived
FROM HPSITE.INSURANCES AS i
LEFT JOIN HPSITE.INSURANCECARRIERS AS c
    ON c.IMRECARRIER_CODE = i.IMRECARRIER_CODE
LEFT JOIN HPSITE.ADDRESSES AS ca
    ON ca.IMREADDR_CODE = c.CARRIER_ADDRCODE
WHERE i.IMREDEM_CODE = :emr_id
