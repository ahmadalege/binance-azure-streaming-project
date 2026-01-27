![Project Architecture](screenshots/2026-01-27%2016_00_23-Excalidraw%20Whiteboard%20-%20Brave.png)

# Real-Time Cryptocurrency Streaming Pipeline on Azure

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Azure](https://img.shields.io/badge/Azure-Event%20Hub-0078D4)
![Databricks](https://img.shields.io/badge/Databricks-Spark-FF3621)
![Delta Lake](https://img.shields.io/badge/Delta%20Lake-Medallion-00ADD8)

A production-grade, real-time data engineering pipeline that streams cryptocurrency trade data from Binance into Azure, processing it through a Medallion Architecture (Bronze → Silver → Gold) using Azure Event Hub, Databricks, and Delta Lake.

## 🎯 Project Overview

This project demonstrates advanced data engineering concepts by building an end-to-end streaming analytics platform for cryptocurrency market data. The pipeline ingests live trade data from Binance, processes it in real-time using Spark Structured Streaming, and creates analytics-ready datasets for business intelligence.

### Business Value

- **Real-time market monitoring** - Track crypto price movements as they happen
- **Historical trend analysis** - Analyze trading patterns across multiple timeframes
- **Automated data quality** - Built-in validation and cleansing
- **Scalable architecture** - Handles high-volume streaming data efficiently

## 🏗️ Architecture

```
   Binance WebSocket API
         ↓
   Python Producer (Async)
         ↓
   Azure Event Hub
         ↓
   Databricks Spark Streaming
         ↓
    ┌──────────────────┐
    │  Bronze Layer    │  (Raw data preservation)
    │  Delta Lake      │
    └────────┬─────────┘
             ↓
    ┌──────────────────┐
    │  Silver Layer    │  (Cleaned & validated)
    │  Delta Lake      │
    └────────┬─────────┘
             ↓
    ┌──────────────────┐
    │   Gold Layer     │  (Business aggregations)
    │  Delta Lake      │
    └──────────────────┘
```

### Technology Stack

| Component       | Technology                   | Purpose                         |
| --------------- | ---------------------------- | ------------------------------- |
| **Data Source** | Binance WebSocket API        | Real-time crypto trade streams  |
| **Ingestion**   | Python (asyncio, websockets) | Async event producer            |
| **Streaming**   | Azure Event Hub              | Managed event streaming service |
| **Processing**  | Azure Databricks             | Spark Structured Streaming      |
| **Storage**     | Delta Lake on Azure Blob     | ACID-compliant data lake        |
| **Compute**     | Apache Spark 3.x             | Distributed stream processing   |
| **Format**      | Parquet + Delta              | Optimized columnar storage      |

## 📊 Data Pipeline Stages

### Bronze Layer (Raw)

- **Purpose**: Immutable raw data preservation
- **Process**: Direct ingestion from Event Hub with minimal transformation
- **Features**:
  - Full audit trail with Event Hub metadata
  - Schema enforcement on write
  - Timestamp tracking (ingestion, event, enqueued)
  - Idempotent writes with checkpointing

### Silver Layer (Cleaned)

- **Purpose**: Validated, cleaned, and enriched data
- **Transformations**:
  - Type conversions (string prices → double)
  - Timestamp parsing (Unix ms → datetime)
  - Derived fields (trade value, base/quote currency)
  - Null filtering and data quality checks
- **Features**:
  - Deduplication logic
  - Schema evolution support
  - Business rules validation

### Gold Layer (Aggregated)

- **Purpose**: Business-ready analytics datasets
- **Aggregations**:
  - **OHLCV candles** (1min, 5min, 15min, 1hour, 1day)
  - **Volume-weighted average price (VWAP)**
  - **Trading volume metrics** by symbol and timeframe
  - **Price volatility indicators**
  - **Market correlation analysis**
- **Features**:
  - Pre-aggregated for query performance
  - Incremental updates every 5 minutes
  - Time-series optimized storage

## 🚀 Getting Started

### Prerequisites

#### Azure Resources

- Azure subscription with Event Hubs namespace
- Azure Databricks workspace (Standard or Premium)
- Azure Blob Storage or ADLS Gen2
- Resource group with appropriate permissions

#### Development Environment

- Python 3.8+
- pip package manager
- Azure CLI (optional, for deployment)

### Installation

#### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/binance-azure-streaming.git
cd binance-azure-streaming
```

#### 2. Set Up Python Producer

```bash
cd producer
pip install -r requirements.txt
```

**Configure Event Hub credentials** in `binance_producer.py`:

```python
EVENT_HUB_CONNECTION_STR = "Endpoint=sb://YOUR_NAMESPACE.servicebus.windows.net/..."
EVENT_HUB_NAME = "binance-trades"
```

**Run the producer**:

```bash
python binance_producer.py
```

Expected output:

```
2024-01-27 10:30:00 - INFO - Connected to Binance WebSocket successfully!
2024-01-27 10:30:05 - INFO - ✅ Sent batch of 10 events (Total: 10)
```

#### 3. Configure Databricks

**Create Databricks Secrets** (recommended for production):

```bash
# Using Databricks CLI
databricks secrets create-scope --scope binance-secrets
databricks secrets put-secret binance-secrets eventhub-access-key
databricks secrets put-secret binance-secrets  storage-account-key
```

**Install Required Libraries**:

1. Go to Databricks Cluster → Libraries
2. Install from Maven:
   ```
   com.microsoft.azure:azure-eventhubs-spark_2.12:2.3.22
   ```
3. Restart cluster

**Configure Storage**:
Update the storage account name in each notebook:

```python
storage_account = "YOUR_STORAGE_ACCOUNT"
container = "YOUR_CONTAINER"
```

#### 4. Run Databricks Notebooks

Import notebooks in order:

1. **01_bronze_layer.ipynb** - Start streaming from Event Hub
2. **02_silver_layer.ipynb** - Clean and transform data
3. **03_gold_layer.ipynb** - Create aggregations

Run cells sequentially in each notebook.

## 🎓 Key Learning Outcomes

This project demonstrates mastery of:

### Data Engineering Concepts

- ✅ Real-time streaming architecture
- ✅ Medallion architecture (Bronze/Silver/Gold)
- ✅ Exactly-once processing semantics
- ✅ Schema evolution and validation
- ✅ Incremental data processing
- ✅ Late-arriving data handling

### Azure & Cloud Services

- ✅ Azure Event Hub (partitioning, consumer groups)
- ✅ Azure Databricks (clusters, notebooks, jobs)
- ✅ Azure Blob Storage / ADLS Gen2
- ✅ Databricks Secrets for credential management
- ✅ Cost optimization strategies

### Apache Spark

- ✅ Structured Streaming
- ✅ Delta Lake ACID transactions
- ✅ Watermarking and windowing
- ✅ Stateful stream processing
- ✅ Checkpoint management

### Python & Async Programming

- ✅ Asyncio for concurrent operations
- ✅ WebSocket client implementation
- ✅ Error handling and retry logic
- ✅ Backpressure management

### Data Quality

- ✅ Schema enforcement
- ✅ Null handling and validation
- ✅ Deduplication strategies
- ✅ Metadata tracking for audit trails

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

Areas for enhancement:

- Additional cryptocurrency exchanges (Coinbase, Kraken)
- Machine learning models for price prediction
- Real-time dashboards with Power BI or Grafana
- Alerting system for price movements
- Historical data backfill capability

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- Binance API for providing free real-time market data
- Azure Databricks documentation and community
- Delta Lake open-source project
- Apache Spark community

## 📧 Contact

**Your Name** - [LinkedIn](https://www.linkedin.com/in/YOUR_PROFILE) | [Email](mailto:your.email@example.com)

**Project Link**: [https://github.com/YOUR_USERNAME/binance-azure-streaming](https://github.com/YOUR_USERNAME/binance-azure-streaming)

---

⭐ **Star this repo** if you found it helpful!

💼 **Hire me** if you need data engineering expertise!
