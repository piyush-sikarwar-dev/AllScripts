-- Pre-2010 records: reactions recorded for the legacy patient's allergies.
SELECT
    d.pat_alrg_key AS allergy_id,
    RTRIM(r.name) AS reaction
FROM conv.cac_pat_alrg AS a
JOIN conv.cac_pat_alrg_det AS d
    ON d.pat_alrg_key = a.pat_alrg_key
JOIN conv.cac_adv_reactions AS r
    ON r.adv_reaction_key = d.adv_reaction_key
WHERE a.patkey = :person_key
