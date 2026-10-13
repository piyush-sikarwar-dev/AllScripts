-- The attachment of one patient-portal message of this patient (bytes).
SELECT
    w.ATTACHMENT AS content,
    w.ATTACHMENT_NAME AS attachment_name,
    w.ATTACHMENT_TYPE AS attachment_type
FROM HPSITE.WEBMESSAGE AS w
WHERE w.WEBMSG_ID = :portal_id
  AND w.IMREDEM_CODE = :emr_id
  AND w.ATTACHMENT IS NOT NULL
