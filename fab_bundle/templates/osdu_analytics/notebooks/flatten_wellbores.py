# Fabric Notebook: Flatten OSDU Wellbore Entities
# Transforms raw OSDU Wellbore JSON with parent well relationships.

from pyspark.sql import functions as F

RAW_TABLE = "osdu_raw_lakehouse.osdu_raw_entities"
WELLBORES_TABLE = "wellbores"

df_raw = (
    spark.read.format("delta").table(RAW_TABLE)
    .filter(F.col("entity_kind_short") == "Wellbore")
)

df_latest = (
    df_raw
    .withColumn("_rn", F.row_number().over(
        F.Window.partitionBy("entity_id")
        .orderBy(F.col("ingestion_timestamp").desc())
    ))
    .filter(F.col("_rn") == 1)
    .drop("_rn")
)

print(f"Processing {df_latest.count()} unique wellbores")

df_wellbores = df_latest.select(
    F.col("entity_id").alias("wellbore_id"),
    F.get_json_object(F.col("entity_json"), "$.data.WellID").alias("well_id"),
    F.get_json_object(F.col("entity_json"), "$.data.FacilityName").alias("wellbore_name"),
    F.get_json_object(F.col("entity_json"), "$.data.WellboreNumber").alias("wellbore_number"),
    F.get_json_object(F.col("entity_json"), "$.data.TrajectoryTypeID").alias("trajectory_type"),
    F.get_json_object(F.col("entity_json"), "$.data.KickOffDepth").cast("double").alias("kickoff_depth_ft"),
    F.get_json_object(F.col("entity_json"), "$.data.TotalDepthMD").cast("double").alias("total_depth_md_ft"),
    F.get_json_object(F.col("entity_json"), "$.data.TotalDepthTVD").cast("double").alias("total_depth_tvd_ft"),
    F.get_json_object(F.col("entity_json"), "$.data.WellboreStatus").alias("wellbore_status"),
    F.get_json_object(F.col("entity_json"), "$.data.TargetFormation").alias("target_formation"),
    F.get_json_object(F.col("entity_json"), "$.data.SpudDate").alias("spud_date_raw"),
    F.get_json_object(F.col("entity_json"), "$.data.CompletionDate").alias("completion_date_raw"),
    F.current_timestamp().alias("_processed_timestamp"),
)

df_wellbores = (
    df_wellbores
    .withColumn("spud_date", F.to_date("spud_date_raw", "yyyy-MM-dd"))
    .withColumn("completion_date", F.to_date("completion_date_raw", "yyyy-MM-dd"))
    .drop("spud_date_raw", "completion_date_raw")
)

df_wellbores.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(WELLBORES_TABLE)

print(f"Wrote {df_wellbores.count()} wellbores to {WELLBORES_TABLE}")
