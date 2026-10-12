-- Lab results for one patient. Dates: observation, else completion, else entry (26% lack an
-- observation date). Status 6 (Canceled) / 7 (Erroneous) are filtered in the repository via config.
SELECT
    r.RESULT_ID AS result_id,
    r.RESULT_NAME AS test,
    r.RESULT_VALUE AS value,
    r.RESULT_UNITS AS units,
    r.RESULT_NORMAL_RANGE AS normal_range,
    r.RESULT_ABNORMAL AS abnormal,
    r.RESULT_FLAGS AS flags,
    r.RESULT_OBSERVATIONDATE AS observed,
    r.RESULT_COMPLETIONDATE AS completed,
    r.TAG_SYSTEMDATE AS recorded,
    r.RESULT_COMPLETIONSTATUS AS status_code,
    r.CORRECTED AS corrected
FROM HPSITE.LAB_RESULT AS r
WHERE r.IMREDEM_CODE = :emr_id
