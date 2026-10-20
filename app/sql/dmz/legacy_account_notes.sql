-- Pre-2010 records: account notes on the legacy patient (conv.patnotes). The staff logins are not read.
SELECT
    n.order_no,
    RTRIM(n.notetype) AS note_type,
    n.entrydt AS entered_at,
    n.editdate AS edited_at,
    RTRIM(n.notetext) AS text,
    RTRIM(n.blinkmsg) AS alert
FROM conv.patnotes AS n
WHERE n.patkey = :person_key
