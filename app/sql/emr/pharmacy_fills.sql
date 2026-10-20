-- Pharmacy fill history from Surescripts (RxHub) for one patient: what pharmacies actually dispensed.
-- RXHUB_REQUEST.PATIENT_ID (indexed) -> RXHUB_MED_HISTORY.RXHUB_ID (indexed). Each request returns the
-- whole history, so the service merges exact repeats.
SELECT
    h.RXHUB_MED_HISTORY_ID AS fill_id,
    r.REQUEST_DATE AS checked_at,
    h.DRUG_NAME AS drug_name,
    h.DRUG_STR AS strength,
    h.DRUG_QTY AS quantity,
    h.DRUG_QTY_UNIT AS quantity_unit,
    h.DRUG_DAYSUPPLY AS days_supply,
    h.DRUG_SIG AS sig,
    h.DRUG_REFILLS AS refills,
    h.SUBSTITUTIONS AS substitutions,
    h.WRITTEN_DATE AS written_date,
    h.LASTFILL_DATE AS last_fill_date,
    h.PROVIDERNAME AS prescriber,
    h.PHARMACY_NAME AS pharmacy
FROM HPSITE.RXHUB_REQUEST AS r
JOIN HPSITE.RXHUB_MED_HISTORY AS h
    ON h.RXHUB_ID = r.RXHUB_ID
WHERE r.PATIENT_ID = :emr_id
