# Enterprise ETL Pipeline
# Reads from source database, writes to lakehouse

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Source configuration (from variables)
# db_host = spark.conf.get("spark.fabric.variables.db_host", "localhost")
# db_name = spark.conf.get("spark.fabric.variables.db_name", "analytics")

# Example: read from SQL source via JDBC
# jdbc_url = f"jdbc:sqlserver://{db_host};databaseName={db_name}"
# df = (
#     spark.read.format("jdbc")
#     .option("url", jdbc_url)
#     .option("dbtable", "dbo.orders")
#     .option("driver", "com.microsoft.sqlserver.jdbc.SQLServerDriver")
#     .load()
# )
# df.write.format("delta").mode("overwrite").saveAsTable("raw_data.orders")

print("ETL pipeline complete")
