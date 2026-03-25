# Fabric Notebook: Process Production Data
# Transforms production volumes into analytics-ready daily/monthly tables.

from pyspark.sql import functions as F

CURATED_WELLS = "osdu_curated_lakehouse.wells"
CURATED_WELLBORES = "osdu_curated_lakehouse.wellbores"
PROD_DAILY_TABLE = "production_daily"
PROD_MONTHLY_TABLE = "production_monthly"

# -----------------------------------------------------------------------
# TODO: Replace with actual production data source
# This creates sample production data for template purposes
# -----------------------------------------------------------------------

from datetime import datetime, timedelta
import random

sample_records = []
wells_df = spark.read.format("delta").table(CURATED_WELLS).select("well_id", "facility_name").collect()

for well in wells_df[:10]:  # Sample first 10 wells
    for day_offset in range(90):
        prod_date = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        sample_records.append({
            "well_id": well["well_id"],
            "production_date": prod_date,
            "oil_bbl": round(random.uniform(50, 500), 2),
            "gas_mcf": round(random.uniform(100, 2000), 2),
            "water_bbl": round(random.uniform(10, 300), 2),
            "choke_size": round(random.uniform(16, 64), 0),
            "tubing_pressure_psi": round(random.uniform(200, 2000), 0),
            "casing_pressure_psi": round(random.uniform(100, 1500), 0),
            "hours_on": round(random.uniform(20, 24), 1),
        })

df_daily = spark.createDataFrame(sample_records)
df_daily = (
    df_daily
    .withColumn("production_date", F.to_date("production_date"))
    .withColumn("gor", F.round(F.col("gas_mcf") / F.col("oil_bbl"), 2))
    .withColumn("water_cut", F.round(F.col("water_bbl") / (F.col("oil_bbl") + F.col("water_bbl")) * 100, 2))
    .withColumn("boe", F.round(F.col("oil_bbl") + F.col("gas_mcf") / 6, 2))
    .withColumn("_processed_timestamp", F.current_timestamp())
)

# -----------------------------------------------------------------------
# Write Daily Production
# -----------------------------------------------------------------------

df_daily.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(PROD_DAILY_TABLE)

print(f"Wrote {df_daily.count()} daily production records")

# -----------------------------------------------------------------------
# Monthly Aggregation
# -----------------------------------------------------------------------

df_monthly = (
    df_daily
    .withColumn("production_month", F.date_trunc("month", "production_date"))
    .groupBy("well_id", "production_month")
    .agg(
        F.sum("oil_bbl").alias("oil_bbl"),
        F.sum("gas_mcf").alias("gas_mcf"),
        F.sum("water_bbl").alias("water_bbl"),
        F.sum("boe").alias("boe"),
        F.avg("gor").alias("avg_gor"),
        F.avg("water_cut").alias("avg_water_cut"),
        F.sum("hours_on").alias("total_hours_on"),
        F.count("*").alias("producing_days"),
        F.avg("tubing_pressure_psi").alias("avg_tubing_pressure"),
    )
    .withColumn("_processed_timestamp", F.current_timestamp())
)

df_monthly.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(PROD_MONTHLY_TABLE)

print(f"Wrote {df_monthly.count()} monthly production records")
