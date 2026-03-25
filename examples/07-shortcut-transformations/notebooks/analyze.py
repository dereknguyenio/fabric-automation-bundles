# Analyze Transformed Data
# All shortcuts are auto-transformed to Delta tables — just query them

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# These tables are auto-populated by shortcut transformations
# No ETL pipeline needed — they stay in sync with the source files

# File transformations
# sales = spark.read.table("raw_data.raw_sales")
# events = spark.read.table("raw_data.raw_events")       # auto-flattened JSON
# products = spark.read.table("raw_data.partner_products")
# finance = spark.read.table("raw_data.finance_monthly")  # from Excel

# AI transformations
# summaries = spark.read.table("documents.ticket_summaries")
# feedback = spark.read.table("documents.feedback_english")
# emails = spark.read.table("documents.classified_emails")

print("All shortcut-transformed tables ready for analysis")
