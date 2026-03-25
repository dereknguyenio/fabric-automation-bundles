# Combine External Sources
# Reads from shortcuts and joins data

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Shortcuts appear as regular tables/files in the lakehouse
# sales = spark.read.table("data_hub.azure_sales_data")
# customers = spark.read.table("data_hub.shared_dimensions")
# partner = spark.read.format("csv").load("Files/partner_feed/")

# enriched = sales.join(customers, "customer_id")
# enriched.write.format("delta").mode("overwrite").saveAsTable("data_hub.enriched_sales")

print("Data combination complete")
