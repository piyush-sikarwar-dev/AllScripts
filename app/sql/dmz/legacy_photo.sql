-- Pre-2010 records: the legacy patient's photo (JPEG bytes).
SELECT TOP 1
    ph.photo
FROM conv.cac_pat_photo AS ph
WHERE ph.patkey = :person_key
