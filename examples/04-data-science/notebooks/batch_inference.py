# Batch Inference
# Score new data using the latest trained model

from pyspark.sql import SparkSession
import mlflow

spark = SparkSession.builder.getOrCreate()

# Example:
# model_uri = "models:/churn_prediction/latest"
# model = mlflow.pyfunc.load_model(model_uri)
#
# new_data = spark.read.table("feature_store.customer_features").toPandas()
# X = new_data.drop(columns=["customer_id", "churned"])
# predictions = model.predict(X)
#
# result = new_data[["customer_id"]].copy()
# result["churn_probability"] = predictions
# spark.createDataFrame(result).write.format("delta").mode("overwrite").saveAsTable("feature_store.churn_scores")

print("Batch inference complete")
