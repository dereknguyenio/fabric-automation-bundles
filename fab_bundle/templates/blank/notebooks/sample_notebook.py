# Sample Notebook
# This notebook is deployed to your Fabric workspace by fab-bundle.
# Edit it here or in the Fabric portal — then redeploy with:
#   fab-bundle deploy -t dev

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.getOrCreate()

# Read from the default lakehouse
# df = spark.read.format("delta").table("my_lakehouse.my_table")
# display(df)

# Example: create a sample table
data = [
    (1, "hello", 100.0),
    (2, "world", 200.0),
    (3, "fabric", 300.0),
]
df = spark.createDataFrame(data, ["id", "name", "value"])

df.write \
    .format("delta") \
    .mode("overwrite") \
    .saveAsTable("sample_table")

print(f"Wrote {df.count()} rows to sample_table")
