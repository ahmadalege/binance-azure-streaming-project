# Architecture Documentation

## System Architecture Overview

This document provides detailed technical architecture of the Real-Time Cryptocurrency Streaming Pipeline.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Binance WebSocket API                        │
│                    (wss://stream.binance.com:9443)                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Trade Events (JSON)
                             │ ~10-50 events/sec per symbol
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Python Async Producer                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐        │
│  │  WebSocket  │→│  Event Queue  │→│  Batch Processor   │         │
│  │   Handler   │  │   (asyncio)   │  │  (10 events/5sec)  │         │
│  └─────────────┘  └──────────────┘  └────────────────────┘         │
└────────────────────────────┬────────────────────────────────────────┘
                             │ AMQP Protocol
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                       Azure Event Hub                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │Partition0│  │Partition1│  │Partition2│  │Partition3│           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│              Retention: 1 day | TU: 1 (1MB/s ingress)              │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Spark Streaming
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Azure Databricks Cluster                          │
│                  (Spark 3.4.1, 2-4 workers)                         │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                    Bronze Layer Pipeline                     │   │
│  │  • Read from Event Hub (micro-batches every 10s)            │   │
│  │  • Parse JSON body                                           │   │
│  │  • Add metadata (timestamps, offsets)                        │   │
│  │  • Write to Delta Lake (append-only)                         │   │
│  │  • Checkpoint: /checkpoints/bronze_binance                   │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                    Silver Layer Pipeline                     │   │
│  │  • Read from Bronze Delta (streaming)                        │   │
│  │  • Filter nulls & validate data                              │   │
│  │  • Type conversions (string → numeric)                       │   │
│  │  • Derive fields (trade_value, timestamps)                   │   │
│  │  • Write to Delta Lake (append-only)                         │   │
│  │  • Checkpoint: /checkpoints/silver_binance                   │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │                     Gold Layer Pipelines                     │   │
│  │  • Read from Silver Delta (streaming)                        │   │
│  │  • Window aggregations (1min, 5min, 15min, 1hr, 1day)      │   │
│  │  • Calculate OHLCV, VWAP, volume metrics                    │   │
│  │  • Write to Delta Lake (upsert for windows)                 │   │
│  │  • Checkpoint: /checkpoints/gold_*                          │   │
│  └────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  Azure Blob Storage / ADLS Gen2                      │
│                                                                      │
│  crypto-data/                                                       │
│  ├── bronze/                                                        │
│  │   └── binance_crypto_raw_v3/                       │
│  │       ├── _delta_log/                                            │
│  │       └── *.parquet                                              │
│  ├── silver/                                                        │
│  │   └── binance_trades_clean/                        │
│  │       ├── _delta_log/                                            │
│  │       └── *.parquet                                              │
│  ├── gold/                                                          │
│  │   ├── ohlcv_1min/                                  │
│  │   ├── ohlcv_5min/                                  │
│  │   ├── ohlcv_1hour/                                 │
│  │   └── vwap/                                        │
│  └── checkpoints/                                                   │
│      ├── bronze_binance/                                            │
│      ├── silver_binance/                                            │
│      └── gold_*/                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Data Source: Binance WebSocket API

**Endpoint**: `wss://stream.binance.com:9443/stream`

**Stream Types**:

- `{symbol}@trade` - Individual trade executions
- `{symbol}@ticker` - 24-hour rolling statistics

**Data Format** (Trade Event):

```json
{
  "e": "trade", // Event type
  "E": 1706354405123, // Event time (ms)
  "s": "BTCUSDT", // Symbol
  "t": 12345, // Trade ID
  "p": "43250.50", // Price
  "q": "0.005", // Quantity
  "b": 88, // Buyer order ID
  "a": 50, // Seller order ID
  "T": 1706354405123, // Trade time (ms)
  "m": true, // Is buyer market maker
  "M": true // Ignore
}
```

**Rate Limits**: None (public streams)
**Latency**: <100ms from trade execution
**Reliability**: Auto-reconnect with exponential backoff

### 2. Python Producer

**Technology**: Python 3.8+ with asyncio

**Key Libraries**:

- `websockets` - WebSocket client
- `azure-eventhub` - Event Hub SDK
- `asyncio` - Async event loop

**Architecture Pattern**: Producer-Consumer with async queue

```python
┌──────────────┐      ┌─────────────┐      ┌────────────────┐
│  WebSocket   │─────→│ asyncio.    │─────→│    Batch       │
│   Streamer   │      │   Queue     │      │  Processor     │
└──────────────┘      └─────────────┘      └────────────────┘
     │                                              │
     │ Receives events                              │ Sends batches
     │ Enriches metadata                            │ to Event Hub
     │ Handles reconnections                        │ (10 events/5s)
     └──────────────────────────────────────────────┘
```

**Error Handling**:

- WebSocket disconnect: Exponential backoff (1s → 60s)
- Event Hub throttle: Automatic retry
- Network issues: Graceful degradation

**Throughput**: ~50-100 events/sec (5 symbols)

### 3. Azure Event Hub

**Configuration**:

- Namespace: Standard tier
- Partitions: 2 (one per worker in Databricks)
- Retention: 1 day
- Throughput Units: 1 (auto-inflate disabled for cost)

**Partitioning Strategy**: Round-robin (default)

- Alternative: Partition by symbol for ordered processing

**Consumer Groups**: `$Default` (Databricks)

**Message Format**:

```json
{
  "source": "binance",
  "stream": "btcusdt@trade",
  "ingestion_timestamp": "2024-01-27T10:30:05.123456Z",
  "event_type": "trade",
  "event_time": 1706354405123,
  "symbol": "BTCUSDT",
  "data": {
    /* trade data */
  }
}
```

### 4. Databricks Streaming Pipeline

**Cluster Configuration**:

```yaml
Runtime: 13.3 LTS (Spark 3.4.1, Scala 2.12)
Driver: Standard_DS3_v2 (14GB RAM, 4 cores)
Workers: 2-4 × Standard_DS3_v2 (autoscaling)
Auto-termination: 30 minutes
Libraries:
  - com.microsoft.azure:azure-eventhubs-spark_2.12:2.3.22
```

### 5. Bronze Layer

**Purpose**: Immutable raw data lake

**Schema**:

```python
root
 |-- eventhub_enqueued_time: timestamp
 |-- eventhub_offset: string
 |-- eventhub_sequence_number: long
 |-- eventhub_partition_key: string
 |-- raw_body: string                      # Full JSON for audit
 |-- bronze_ingestion_time: timestamp      # Spark processing time
 |-- bronze_source_system: string          # "eventhub"
 |-- source: string                        # "binance"
 |-- stream: string                        # "btcusdt@trade"
 |-- ingestion_timestamp: string           # Producer timestamp
 |-- event_type: string                    # "trade"
 |-- event_time: long                      # Binance event time (ms)
 |-- symbol: string                        # "BTCUSDT"
 |-- trade_id: long
 |-- trade_price: string
 |-- trade_quantity: string
 |-- buyer_order_id: long
 |-- seller_order_id: long
 |-- trade_time: long
 |-- is_buyer_maker: boolean
 |-- is_best_match: boolean
```

**Processing**:

- Trigger: 10 seconds
- Mode: Append-only
- Checkpoint: Every micro-batch
- Average batch size: 50-500 events

**Performance**:

- Throughput: ~100-500 events/sec
- Latency: 10-15 seconds (trigger + processing)
- Storage: ~10GB/day (5 symbols)

### 6. Silver Layer

**Purpose**: Cleaned, validated, business-ready data

**Transformations**:

```python
1. Filter null records
2. Cast string prices → double
3. Calculate trade_value = price × quantity
4. Parse timestamps (Unix ms → timestamp)
5. Extract base/quote currency from symbol
6. Add processing metadata
```

**Schema**:

```python
root
 |-- trade_id: long
 |-- symbol: string
 |-- base_currency: string         # "BTC" from "BTCUSDT"
 |-- quote_currency: string        # "USDT" from "BTCUSDT"
 |-- trade_timestamp: timestamp
 |-- event_timestamp: timestamp
 |-- trade_date: date
 |-- trade_hour: integer
 |-- price: double                 # Numeric conversion
 |-- quantity: double              # Numeric conversion
 |-- trade_value_usd: double       # price × quantity
 |-- is_buyer_maker: boolean
 |-- buyer_order_id: long
 |-- seller_order_id: long
 |-- bronze_ingestion_time: timestamp
 |-- silver_processing_time: timestamp
```

## Future Enhancements

1. **Real-time ML**: Integrate price prediction models
2. **Multi-exchange**: Add Coinbase, Kraken streams
3. **Advanced analytics**: Correlation matrices, arbitrage detection
4. **Real-time alerts**: Price threshold notifications
5. **Dashboard**: Power BI/Grafana for visualization
6. **API layer**: Serve Gold layer via REST API

---

**Document Version**: 1.0  
**Last Updated**: January 27, 2024  
**Author**: Ahmad Olaitan Alege
