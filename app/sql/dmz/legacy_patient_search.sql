-- Pre-2010 records: one page (25) of legacy patients (DMZ conv.person), by last name.
-- Filters: name prefixes (pre-escaped, LIKE ... ESCAPE '!'), date of birth, legacy patient id.
-- ssno is never selected (CLAUDE.md §4.4).
SELECT
    p.personkey AS person_key,
    RTRIM(p.lname) AS last_name,
    RTRIM(p.fname) AS first_name,
    RTRIM(p.mi) AS middle_initial,
    p.birthdate AS dob,
    RTRIM(p.sex) AS sex,
    RTRIM(p.patid) AS legacy_id,
    COUNT(*) OVER () AS total_count
FROM conv.person AS p
WHERE (:last_name_like IS NULL OR p.lname LIKE :last_name_like ESCAPE '!')
  AND (:first_name_like IS NULL OR p.fname LIKE :first_name_like ESCAPE '!')
  AND (:dob IS NULL OR CAST(p.birthdate AS date) = :dob)
  AND (:legacy_id IS NULL OR RTRIM(p.patid) = :legacy_id)
ORDER BY p.lname, p.fname, p.personkey
OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
OPTION (RECOMPILE)
