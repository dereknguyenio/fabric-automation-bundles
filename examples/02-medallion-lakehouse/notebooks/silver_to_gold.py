# Silver to Gold
# Aggregates and curates data for business consumption

from pyspark.sql import SparkSession
from pyspark.sql.functions import sum, count, avg

spark = SparkSession.builder.getOrCreate()

# Example: daily order summary
# silver_orders = spark.read.table("silver.orders")
# gold_daily_summary = (
#     silver_orders
#     .groupBy("order_date")
#     .agg(
#         count("order_id").alias("total_orders"),
#         sum("total_amount").alias("revenue"),
#         avg("total_amount").alias("avg_order_value"),
#     )
# )
# gold_daily_summary.write.format("delta").mode("overwrite").saveAsTable("gold.daily_order_summary")

print("Gold aggregation complete")
