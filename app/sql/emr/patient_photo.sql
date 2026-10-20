-- One patient's photo (JPEG bytes).
SELECT TOP 1 pic.DEM_PICTURE AS photo
FROM HPSITE.DEMOGRAPHICPICTURE AS pic
WHERE pic.IMREDEM_CODE = :emr_id
