# Model Training with MLflow
# Trains a model and logs metrics to Fabric ML experiment

from pyspark.sql import SparkSession
import mlflow

spark = SparkSession.builder.getOrCreate()

model_type = spark.conf.get("spark.fabric.params.model_type", "xgboost")
n_estimators = int(spark.conf.get("spark.fabric.params.n_estimators", "100"))
learning_rate = float(spark.conf.get("spark.fabric.params.learning_rate", "0.1"))

print(f"Training {model_type} model (n_estimators={n_estimators}, lr={learning_rate})")

# Example MLflow tracking:
# mlflow.set_experiment("churn_prediction")
# with mlflow.start_run():
#     mlflow.log_params({"model_type": model_type, "n_estimators": n_estimators})
#
#     features = spark.read.table("feature_store.customer_features").toPandas()
#     X = features.drop(columns=["customer_id", "churned"])
#     y = features["churned"]
#
#     from sklearn.model_selection import train_test_split
#     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
#
#     if model_type == "xgboost":
#         from xgboost import XGBClassifier
#         model = XGBClassifier(n_estimators=n_estimators, learning_rate=learning_rate)
#     model.fit(X_train, y_train)
#
#     accuracy = model.score(X_test, y_test)
#     mlflow.log_metric("accuracy", accuracy)
#     mlflow.sklearn.log_model(model, "model")
#     print(f"Accuracy: {accuracy:.4f}")

print("Training complete")
