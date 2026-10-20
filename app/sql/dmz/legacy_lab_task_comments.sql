-- Pre-2010 records: staff follow-up comments on the legacy patient's lab results
-- (Orders.TaskQueueComments.order_or_result_no = cac_results.sysresultno). The author login is not read.
SELECT
    q.order_or_result_no AS result_id,
    q.comment_sequence AS line_no,
    q.comment,
    q.create_datetime AS created_at
FROM Orders.LabOrders AS o
JOIN Orders.LabTests AS t
    ON t.sysorderno = o.sysorderno
JOIN conv.cac_results AS r
    ON r.systestordered = t.systestorderno
JOIN Orders.TaskQueueComments AS q
    ON q.order_or_result_no = r.sysresultno
WHERE o.patkey = :person_key
