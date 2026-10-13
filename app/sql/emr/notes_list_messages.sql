-- Notes tab index: phone / patient messages and refill requests saved to the patient's chart
-- (HPSITE.MESSAGE_SAVED; the live inbox HPSITE.MESSAGE is workflow, not chart). Metadata only.
SELECT
    m.IMREMESSAGE_CODE AS message_id,
    m.MSG_TRANSACTIONDATE AS sent,
    m.MSG_TYPE AS msg_type,
    m.MSG_SUBJECT AS subject,
    e.IMREENC_CODE AS encounter_id,
    pf.PROV_LASTNAME AS from_last,
    pf.PROV_FIRSTNAME AS from_first,
    pf.PROV_TITLE AS from_title
FROM HPSITE.MESSAGE_SAVED AS m
LEFT JOIN HPSITE.ENCOUNTER AS e
    ON e.IMREENC_CODE = m.IMREENC_CODE
   AND e.IMREDEMEC_CODE = m.IMREDEM_CODE
LEFT JOIN HPSITE.PROVIDERS AS pf
    ON pf.IMREPROV_CODE = m.MSG_FROMPROVCODE
WHERE m.IMREDEM_CODE = :emr_id
