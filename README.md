<div align="center">

# 🚨 High-Frequency Market Manipulation & Anomaly Detector
**Real-Time Risk AI Engine for detecting spoofing, quote stuffing, and layering in L2 Order Books.**

![C++20](https://img.shields.io/badge/C++20-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Python 3.10+](https://img.shields.io/badge/Python_3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Apache Spark](https://img.shields.io/badge/Apache_Spark-E25A1C?style=for-the-badge&logo=apache-spark&logoColor=white)
![DuckDB](https://img.shields.io/badge/DuckDB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black)
![Scikit-Learn](https://img.shields.io/badge/Scikit_Learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)

</div>

> [!NOTE]
> This engine is designed to parse massive volumes of L2 tick streams (50,000+ events) with sub-millisecond latency. It extracts real-time manipulation signals and uses rolling PySpark/SQL pipelines to feed strict False-Positive constrained anomaly detection models.

---

## ⚡ Architecture & Data Flow

```mermaid
graph LR
    A[L2 Tick Data Stream\n Order Events & Trades] -->|Sub-millisecond| B(C++20 Feature Extractor\n OrderEventTracker)
    B -->|PyBind11| C[PySpark & DuckDB\n Feature Engineering]
    C --> D[Z-Score / Isolation Forest\n Anomaly Detector]
