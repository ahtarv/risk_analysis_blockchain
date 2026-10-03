

from pyspark.sql import SparkSession
from pyspark.sql.window import Window
import pyspark.sql.functions as F
import pandas as pd

class PySparkFeaturePipeline:
    def __init__(self, app_name="RiskAIFeaturePipeline"):
        self.spark = SparkSession.builder \
            .appName(app_name) \
            .config("spark.driver.memory", "4g") \
            .getOrCreate()
        self.df_spark = None

    def ingest_pandas(self, pdf: pd.DataFrame):

        pdf['submit_sec'] = pdf['submit_us'] / 1e6
        self.df_spark = self.spark.createDataFrame(pdf)

    def compute_features(self):

        if self.df_spark is None:
            raise ValueError("No data ingested. Call ingest_pandas() first.")

        w_1m = Window.partitionBy("symbol").orderBy("submit_sec").rangeBetween(-60, 0)

        df = self.df_spark.withColumn(
            "orders_1m", F.count("order_id").over(w_1m)
        ).withColumn(
            "fills_1m", F.sum(F.when(F.col("filled") == True, 1).otherwise(0)).over(w_1m)
        )

        df = df.withColumn(
            "otr_1m", F.col("orders_1m") / (F.col("fills_1m") + 1)
        )

        df = df.withColumn(
            "cancels_1m", F.sum(F.when(F.col("cancel_us") > 0, 1).otherwise(0)).over(w_1m)
        ).withColumn(
            "cfr_1m", F.col("cancels_1m") / (F.col("fills_1m") + 1)
        )

        return df.toPandas()

if __name__ == "__main__":
    print("[PySpark] Initializing feature engineering pipeline...")
    pipe = PySparkFeaturePipeline()
    print("[PySpark] Session ready. Can process billions of records distributedly.")
