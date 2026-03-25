# Fabric Notebook: Ingest to Bronze
# This notebook ingests raw data from source systems into the bronze lakehouse.
# Data is landed as-is with minimal transformation (append-only pattern).

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

SOURCE_TABLE = "raw_data"
BRONZE_TABLE = "bronze_raw_data"

# -----------------------------------------------------------------------
# Ingestion
# -----------------------------------------------------------------------

# TODO: Replace with your actual data source
# Example: Read from ADLS shortcut, API, or database

# df = spark.read.format("delta").load("abfss://container@account.dfs.core.windows.net/path")

# For demo: create sample data
from pyspark.sql import functions as F
from datetime import datetime

sample_data = [
    (1, "record_1", datetime.now().isoformat(), 100.0),
    (2, "record_2", datetime.now().isoformat(), 200.0),
    (3, "record_3", datetime.now().isoformat(), 300.0),
]

df = spark.createDataFrame(sample_data, ["id", "name", "ingested_at", "value"])

# Add ingestion metadata
df_with_metadata = df.withColumn("_ingestion_timestamp", F.current_timestamp()) \
                     .withColumn("_source_file", F.lit("sample_source"))

# -----------------------------------------------------------------------
# Write to Bronze (append-only)
# -----------------------------------------------------------------------

df_with_metadata.write \
    .format("delta") \
    .mode("append") \
    .saveAsTable(BRONZE_TABLE)

print(f"Ingested {df_with_metadata.count()} records to {BRONZE_TABLE}")
