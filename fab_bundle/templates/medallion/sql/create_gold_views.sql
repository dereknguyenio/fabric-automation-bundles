-- Gold Layer SQL Views
-- These views provide a SQL-friendly interface over gold lakehouse tables.

-- Daily summary with running totals
CREATE OR ALTER VIEW vw_daily_summary AS
SELECT
    date,
    record_count,
    total_value,
    avg_value,
    min_value,
    max_value,
    SUM(total_value) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS cumulative_value,
    SUM(record_count) OVER (ORDER BY date ROWS UNBOUNDED PRECEDING) AS cumulative_records
FROM gold_lakehouse.dbo.gold_daily_summary;

-- Latest snapshot with business-friendly column names  
CREATE OR ALTER VIEW vw_current_state AS
SELECT
    id AS record_id,
    name AS record_name,
    value AS current_value,
    ingested_at AS last_updated
FROM gold_lakehouse.dbo.gold_latest_snapshot;
