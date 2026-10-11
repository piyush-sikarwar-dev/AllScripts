-- What the connected login is allowed to do in the current database (1 = yes).
SELECT
    IS_SRVROLEMEMBER('sysadmin') AS is_sysadmin,
    IS_ROLEMEMBER('db_owner') AS is_db_owner,
    IS_ROLEMEMBER('db_datareader') AS is_datareader,
    IS_ROLEMEMBER('db_datawriter') AS is_datawriter,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'INSERT') AS can_insert,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'UPDATE') AS can_update,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'DELETE') AS can_delete,
    HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'ALTER') AS can_alter
