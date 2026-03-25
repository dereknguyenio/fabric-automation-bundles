# Fabric Notebook: Silver to Gold
# Aggregates and curates silver data into business-ready gold datasets.

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

SILVER_TABLE = "silver_lakehouse.silver_clean_data"
GOLD_SUMMARY_TABLE = "gold_daily_summary"
GOLD_LATEST_TABLE = "gold_latest_snapshot"

# -----------------------------------------------------------------------
# Read Silver
# -----------------------------------------------------------------------

from pyspark.sql import functions as F

df_silver = spark.read.format("delta").table(SILVER_TABLE)

print(f"Read {df_silver.count()} records from silver")

# -----------------------------------------------------------------------
# Gold: Daily Summary (aggregation)
# -----------------------------------------------------------------------

df_daily = (
    df_silver
    .withColumn("date", F.to_date("ingested_at"))
    .groupBy("date")
    .agg(
        F.count("*").alias("record_count"),
        F.sum("value").alias("total_value"),
        F.avg("value").alias("avg_value"),
        F.min("value").alias("min_value"),
        F.max("value").alias("max_value"),
    )
    .withColumn("_gold_timestamp", F.current_timestamp())
    .orderBy("date")
)

df_daily.write \
    .format("delta") \
    .mode("overwrite") \
    .saveAsTable(GOLD_SUMMARY_TABLE)

print(f"Wrote {df_daily.count()} daily summary records to {GOLD_SUMMARY_TABLE}")

# -----------------------------------------------------------------------
# Gold: Latest Snapshot (current state)
# -----------------------------------------------------------------------

df_latest = (
    df_silver
    .withColumn(
        "_row_num",
        F.row_number().over(
            F.Window.partitionBy("id").orderBy(F.col("_silver_timestamp").desc())
        ),
    )
    .filter(F.col("_row_num") == 1)
    .drop("_row_num", "_ingestion_timestamp", "_silver_timestamp", "_source_file", "_is_valid")
    .withColumn("_gold_timestamp", F.current_timestamp())
)

df_latest.write \
    .format("delta") \
    .mode("overwrite") \
    .saveAsTable(GOLD_LATEST_TABLE)

print(f"Wrote {df_latest.count()} snapshot records to {GOLD_LATEST_TABLE}")
