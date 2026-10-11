-- Metadata only: server version and current database. No patient data.
SELECT
    CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(128)) AS product_version,
    CAST(SERVERPROPERTY('Edition') AS nvarchar(128)) AS edition,
    DB_NAME() AS database_name
