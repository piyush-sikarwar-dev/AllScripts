-- One saved message of this patient with its text (latest revision of NOTES_TEXTDATA).
SELECT
    m.IMREMESSAGE_CODE AS message_id,
    m.MSG_TRANSACTIONDATE AS sent,
    m.MSG_TYPE AS msg_type,
    m.MSG_SUBJECT AS subject,
    m.MSG_PHONENUMBER AS phone,
    m.MSG_TOADDRESSEES AS to_addressees,
    pf.PROV_LASTNAME AS from_last,
    pf.PROV_FIRSTNAME AS from_first,
    pf.PROV_TITLE AS from_title,
    pt.PROV_LASTNAME AS to_last,
    pt.PROV_FIRSTNAME AS to_first,
    pt.PROV_TITLE AS to_title,
    t.NOTE_TEXT AS body
FROM HPSITE.MESSAGE_SAVED AS m
LEFT JOIN HPSITE.PROVIDERS AS pf
    ON pf.IMREPROV_CODE = m.MSG_FROMPROVCODE
LEFT JOIN HPSITE.PROVIDERS AS pt
    ON pt.IMREPROV_CODE = m.MSG_TOPROVCODE
OUTER APPLY (
    SELECT TOP 1 n.NOTE_TEXT
    FROM HPSITE.NOTES_TEXTDATA AS n
    WHERE n.IMRENOTE_CODE = m.IMRENOTE_CODE
    ORDER BY n.TAG_REVISION DESC
) AS t
WHERE m.IMREMESSAGE_CODE = :message_id
  AND m.IMREDEM_CODE = :emr_id
