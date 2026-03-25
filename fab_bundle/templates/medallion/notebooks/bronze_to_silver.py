# Fabric Notebook: Bronze to Silver
# Cleans, validates, deduplicates, and conforms bronze data into silver.

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

BRONZE_TABLE = "bronze_lakehouse.bronze_raw_data"
SILVER_TABLE = "silver_clean_data"

# -----------------------------------------------------------------------
# Read Bronze
# -----------------------------------------------------------------------

from pyspark.sql import functions as F

df_bronze = spark.read.format("delta").table(BRONZE_TABLE)

print(f"Read {df_bronze.count()} records from bronze")

# -----------------------------------------------------------------------
# Clean & Validate
# -----------------------------------------------------------------------

df_cleaned = (
    df_bronze
    # Remove nulls in key columns
    .filter(F.col("id").isNotNull())
    .filter(F.col("name").isNotNull())
    # Deduplicate by id (keep latest ingestion)
    .withColumn(
        "_row_num",
        F.row_number().over(
            F.Window.partitionBy("id").orderBy(F.col("_ingestion_timestamp").desc())
        ),
    )
    .filter(F.col("_row_num") == 1)
    .drop("_row_num")
    # Standardize types
    .withColumn("value", F.col("value").cast("decimal(18,2)"))
    .withColumn("ingested_at", F.to_timestamp("ingested_at"))
    # Add silver metadata
    .withColumn("_silver_timestamp", F.current_timestamp())
    .withColumn("_is_valid", F.lit(True))
)

# -----------------------------------------------------------------------
# Data Quality Checks
# -----------------------------------------------------------------------

total = df_cleaned.count()
null_values = df_cleaned.filter(F.col("value").isNull()).count()

print(f"Silver records: {total}")
print(f"Null values: {null_values}")

if null_values > total * 0.1:
    print("WARNING: >10% null values detected")

# -----------------------------------------------------------------------
# Write to Silver (merge/upsert)
# -----------------------------------------------------------------------

df_cleaned.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(SILVER_TABLE)

print(f"Wrote {total} records to {SILVER_TABLE}")
