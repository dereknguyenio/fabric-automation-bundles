# Bronze to Silver
# Cleans, validates, deduplicates, and types raw data

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, trim, lower, current_timestamp

spark = SparkSession.builder.getOrCreate()

# Example: clean orders
# bronze_orders = spark.read.table("bronze.raw_orders")
# silver_orders = (
#     bronze_orders
#     .dropDuplicates(["order_id"])
#     .filter(col("order_id").isNotNull())
#     .withColumn("customer_email", lower(trim(col("customer_email"))))
#     .withColumn("processed_at", current_timestamp())
# )
# silver_orders.write.format("delta").mode("overwrite").saveAsTable("silver.orders")

print("Silver transformation complete")
