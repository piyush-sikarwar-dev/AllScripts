-- Row count from catalog metadata (sys.partitions): fast, reads no table data.
SELECT SUM(p.rows) AS row_count
FROM sys.partitions AS p
JOIN sys.tables AS t ON t.object_id = p.object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE s.name = :schema_name
  AND t.name = :table_name
  AND p.index_id IN (0, 1)
