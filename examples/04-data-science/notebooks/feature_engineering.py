# Feature Engineering
# Build ML features from raw lakehouse data

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, datediff, current_date, count, sum as _sum, avg

spark = SparkSession.builder.getOrCreate()

# Example: customer features for churn prediction
# orders = spark.read.table("feature_store.orders")
# customers = spark.read.table("feature_store.customers")
#
# features = (
#     orders
#     .groupBy("customer_id")
#     .agg(
#         count("order_id").alias("total_orders"),
#         _sum("amount").alias("total_spend"),
#         avg("amount").alias("avg_order_value"),
#         datediff(current_date(), max("order_date")).alias("days_since_last_order"),
#     )
#     .join(customers, "customer_id")
# )
# features.write.format("delta").mode("overwrite").saveAsTable("feature_store.customer_features")

print("Feature engineering complete")
