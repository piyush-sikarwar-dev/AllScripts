-- Appointments tab: the patient's practice-management appointments with decoded type, provider
-- (resource), location and cancellation reason. Operator (staff) columns are not selected.
SELECT
    a.Appointment_ID AS pm_id,
    a.Appointment_DateTime AS starts,
    a.Duration AS duration,
    a.Status AS status,
    a.Comments AS comment,
    a.Time_In AS time_in,
    a.Check_Out_Time AS check_out,
    a.DateTime_Cancelled AS cancelled_at,
    a.DateTime_NoShow AS no_show_at,
    t.Description AS appt_type,
    r.Description AS resource,
    l.Description AS location,
    c.Description AS cancel_reason
FROM PM.Appointments AS a
LEFT JOIN PM.Appointment_Types AS t
    ON t.Appointment_Type_ID = a.Appointment_Type_ID
LEFT JOIN PM.Resources AS r
    ON r.Resource_ID = a.Resource_ID
LEFT JOIN PM.Scheduling_Locations AS l
    ON l.Scheduling_Location_ID = a.Scheduling_Location_ID
LEFT JOIN PM.Cancellation_Reasons AS c
    ON c.Cancellation_Reason_ID = a.Cancellation_Reason_ID
WHERE a.Patient_ID = :ntier_id
  AND ISNULL(a.Is_Memo_Appointment, 0) = 0
