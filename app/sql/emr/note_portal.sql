-- One patient-portal message of this patient (saved copy first, else the portal mailbox copy).
-- The attachment bytes are read separately (note_portal_attachment.sql).
SELECT TOP 1
    x.portal_id,
    x.sent,
    x.msg_type,
    x.subject,
    x.body,
    x.prov_last,
    x.prov_first,
    x.prov_title,
    x.attachment_name,
    x.has_attachment
FROM (
    SELECT
        s.WEBMSG_ID AS portal_id,
        s.TAG_SYSTEMDATE AS sent,
        s.MSG_TYPE AS msg_type,
        s.SUBJECT AS subject,
        s.BODY_TEXT AS body,
        p.PROV_LASTNAME AS prov_last,
        p.PROV_FIRSTNAME AS prov_first,
        p.PROV_TITLE AS prov_title,
        s.ATTACHMENT_NAME AS attachment_name,
        CASE WHEN w.ATTACHMENT IS NULL THEN 0 ELSE 1 END AS has_attachment,
        1 AS pref
    FROM HPSITE.WEBMESSAGE_SAVED AS s
    LEFT JOIN HPSITE.WEBMESSAGE AS w
        ON w.WEBMSG_ID = s.WEBMSG_ID
    LEFT JOIN HPSITE.PROVIDERS AS p
        ON p.IMREPROV_CODE = COALESCE(NULLIF(s.ORIG_PROVCODE, 0), s.IMREPROV_CODE)
    WHERE s.WEBMSG_ID = :portal_id
      AND s.IMREDEM_CODE = :emr_id
    UNION ALL
    SELECT
        w.WEBMSG_ID,
        w.TAG_SYSTEMDATE,
        w.MSG_TYPE,
        w.SUBJECT,
        w.BODY_TEXT,
        p.PROV_LASTNAME,
        p.PROV_FIRSTNAME,
        p.PROV_TITLE,
        w.ATTACHMENT_NAME,
        CASE WHEN w.ATTACHMENT IS NULL THEN 0 ELSE 1 END,
        2
    FROM HPSITE.WEBMESSAGE AS w
    LEFT JOIN HPSITE.PROVIDERS AS p
        ON p.IMREPROV_CODE = COALESCE(NULLIF(w.ORIG_PROVCODE, 0), w.IMREPROV_CODE)
    WHERE w.WEBMSG_ID = :portal_id
      AND w.IMREDEM_CODE = :emr_id
) AS x
ORDER BY x.pref
