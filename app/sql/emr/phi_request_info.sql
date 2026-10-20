-- What each Allscripts release request asked for (PHIRQST_INFO dictionary codes).
SELECT
    i.REQUESTID AS request_id,
    i.DICTCODE AS code
FROM HPSITE.PHIREQUEST_REQUESTEDINFO AS i
