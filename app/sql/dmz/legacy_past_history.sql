-- Pre-2010 records: past medical / surgical / family / social history entries (dbo.Gloss_base;
-- categorycode uses the same codes as EMR HX_DIAGNOSIS.CATEGORY_CODE).
SELECT
    g.glossarylayoutkey AS layout_key,
    g.rownum AS row_no,
    g.categorycode AS category_code,
    RTRIM(g.hxkndgcodeChar) AS code,
    RTRIM(g.hx_element) AS item,
    g.glossary_text AS glossary_text,
    g.ChartText AS chart_text,
    g.service_datetime AS recorded_at,
    g.note_id,
    RTRIM(d.lname) AS provider_last,
    RTRIM(d.fname) AS provider_first,
    RTRIM(d.title) AS provider_title
FROM dbo.Gloss_base AS g
LEFT JOIN conv.drmast AS d
    ON d.drno = g.drno
WHERE g.patkey = :person_key
