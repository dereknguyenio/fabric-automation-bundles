# Ingest to Bronze
# Reads raw data and lands it in the bronze lakehouse as Delta tables

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Parameters (overridable via fab-bundle run --param)
source_path = spark.conf.get("spark.fabric.params.source_path", "/mnt/raw")
batch_date = spark.conf.get("spark.fabric.params.batch_date", "2024-01-01")

print(f"Ingesting from {source_path} for batch {batch_date}")

# Example: read CSV files from source
# df = spark.read.csv(f"{source_path}/orders/*.csv", header=True, inferSchema=True)
# df.write.format("delta").mode("append").saveAsTable("bronze.raw_orders")

# Example: read JSON files
# df = spark.read.json(f"{source_path}/events/*.json")
# df.write.format("delta").mode("append").saveAsTable("bronze.raw_events")

print("Bronze ingestion complete")
