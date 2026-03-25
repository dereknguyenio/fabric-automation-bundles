# Fabric Notebook: Flatten OSDU Well Entities
# Transforms raw OSDU Well JSON into typed, queryable Delta tables.

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

RAW_TABLE = "osdu_raw_lakehouse.osdu_raw_entities"
WELLS_TABLE = "wells"
WELL_HEADERS_TABLE = "well_headers"

# -----------------------------------------------------------------------
# Read latest raw well data
# -----------------------------------------------------------------------

df_raw = (
    spark.read.format("delta").table(RAW_TABLE)
    .filter(F.col("entity_kind_short") == "Well")
    .withColumn("entity", F.from_json(F.col("entity_json"), "MAP<STRING, STRING>"))
)

# Get latest version per entity_id
df_latest = (
    df_raw
    .withColumn("_rn", F.row_number().over(
        F.Window.partitionBy("entity_id")
        .orderBy(F.col("ingestion_timestamp").desc())
    ))
    .filter(F.col("_rn") == 1)
    .drop("_rn")
)

print(f"Processing {df_latest.count()} unique wells")

# -----------------------------------------------------------------------
# Flatten Well entity JSON
# -----------------------------------------------------------------------

# Parse the full JSON for nested field extraction
df_parsed = df_latest.withColumn("data", F.from_json(F.col("entity_json"), "MAP<STRING, STRING>"))

df_wells = df_parsed.select(
    F.col("entity_id").alias("well_id"),
    F.get_json_object(F.col("entity_json"), "$.data.FacilityName").alias("facility_name"),
    F.get_json_object(F.col("entity_json"), "$.data.FacilityOperator").alias("operator"),
    F.get_json_object(F.col("entity_json"), "$.data.CountryID").alias("country"),
    F.get_json_object(F.col("entity_json"), "$.data.StateProvinceID").alias("state_province"),
    F.get_json_object(F.col("entity_json"), "$.data.CountyID").alias("county"),
    F.get_json_object(F.col("entity_json"), "$.data.FieldID").alias("field_name"),
    F.get_json_object(F.col("entity_json"), "$.data.BasinID").alias("basin"),
    F.get_json_object(F.col("entity_json"), "$.data.CurrentOperator").alias("current_operator"),
    F.get_json_object(F.col("entity_json"), "$.data.WellStatus").alias("well_status"),
    F.get_json_object(F.col("entity_json"), "$.data.SpudDate").alias("spud_date_raw"),
    F.get_json_object(F.col("entity_json"), "$.data.SurfaceLocation.Latitude").cast("double").alias("surface_latitude"),
    F.get_json_object(F.col("entity_json"), "$.data.SurfaceLocation.Longitude").cast("double").alias("surface_longitude"),
    F.get_json_object(F.col("entity_json"), "$.data.TotalDepth").cast("double").alias("total_depth_ft"),
    F.get_json_object(F.col("entity_json"), "$.data.UWI").alias("uwi"),
    F.get_json_object(F.col("entity_json"), "$.data.API").alias("api_number"),
    F.current_timestamp().alias("_processed_timestamp"),
)

# Type conversions
df_wells = df_wells.withColumn(
    "spud_date",
    F.to_date(F.col("spud_date_raw"), "yyyy-MM-dd")
).drop("spud_date_raw")

# -----------------------------------------------------------------------
# Write to Curated Lakehouse
# -----------------------------------------------------------------------

df_wells.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(WELLS_TABLE)

print(f"Wrote {df_wells.count()} wells to {WELLS_TABLE}")

# -----------------------------------------------------------------------
# Well Headers (denormalized view for BI)
# -----------------------------------------------------------------------

df_headers = df_wells.select(
    "well_id", "facility_name", "uwi", "api_number",
    "operator", "current_operator", "well_status",
    "field_name", "basin", "state_province", "county", "country",
    "surface_latitude", "surface_longitude",
    "spud_date", "total_depth_ft",
)

df_headers.write \
    .format("delta") \
    .mode("overwrite") \
    .saveAsTable(WELL_HEADERS_TABLE)

print(f"Wrote {df_headers.count()} well headers to {WELL_HEADERS_TABLE}")
