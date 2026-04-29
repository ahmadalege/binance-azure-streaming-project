# Real-Time Cryptocurrency Market Data Streaming Platform

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Azure](https://img.shields.io/badge/Azure-Event%20Hub-0078D4)
![Databricks](https://img.shields.io/badge/Databricks-Spark-FF3621)
![Delta Lake](https://img.shields.io/badge/Delta%20Lake-Medallion-00ADD8)

## System Overview

This is a continuous real-time data streaming platform that ingests high-frequency cryptocurrency market data from Binance's WebSocket API, processes it with low-latency requirements through a distributed Apache Spark pipeline on Azure Databricks, and maintains a Medallion architecture in Delta Lake for scalable analytics. The system operates 24/7, handling sustained event rates of 50,000+ trades per minute across multiple symbols with end-to-end latency under 5 seconds.

### Real-Time Constraints
- **Event Frequency**: 10-50 trades/second per symbol during normal market hours, spiking to 200+ during volatility
- **Latency Target**: <5 seconds from trade execution to analytics availability
- **Throughput**: Sustained processing of 100,000+ events/minute across all symbols
- **Data Freshness**: Market data available within 1 second of API receipt

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Data Source Layer                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Binance WebSocket API                           │   │
│  │  • Real-time trade streams (wss://stream.binance.com)       │   │
│  │  • Multiple symbols (BTC/USDT, ETH/USDT, etc.)               │   │
│  │  • JSON event format with trade metadata                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ WebSocket Stream
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Ingestion Layer                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │               Azure Event Hub                                 │   │
│  │  • Managed event streaming service                           │   │
│  │  • 32 partitions for parallel processing                      │   │
│  │  • 7-day retention with capture to ADLS                       │   │
│  │  • Throughput units: 20 TU (2MB/s ingress)                    │   │
│  └─────────────────────────────┬──────────────────────────────────┘   │
│                                │ Kafka Protocol
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Python Producer (Async)                          │   │
│  │  • AsyncIO WebSocket client                                 │   │
│  │  • Event batching (50 events/100ms)                         │   │
│  │  • Connection pooling and reconnection logic                │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Structured Streaming
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                  Processing Layer                                   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Azure Databricks (Spark Streaming)               │   │
│  │  • Spark 3.4 Structured Streaming                            │   │
│  │  • Micro-batch processing (10-second triggers)               │   │
│  │  • Auto-scaling cluster (2-20 workers)                       │   │
│  │  • Photon engine for accelerated processing                  │   │
│  └─────────────────────────────┬──────────────────────────────────┘   │
│                                │ Delta Lake Writes
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Bronze Layer (Raw Streaming)                     │   │
│  │  • Append-only raw events with full fidelity                │   │
│  │  • Partitioned by date/hour/symbol                           │   │
│  │  • Metadata enrichment (ingestion timestamps)               │   │
│  └─────────────────────────────┬──────────────────────────────────┘   │
│                                │ Streaming Transformations
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Silver Layer (Cleaned Streaming)                 │   │
│  │  • Schema validation and type conversion                    │   │
│  │  • Deduplication and data quality checks                    │   │
│  │  • Watermarking for late-arriving data                      │   │
│  └─────────────────────────────┬──────────────────────────────────┘   │
│                                │ Windowed Aggregations
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Gold Layer (Analytics Streaming)                 │   │
│  │  • Real-time OHLCV calculations                             │   │
│  │  • VWAP and volume metrics                                   │   │
│  │  • Market indicators and correlations                       │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Analytics Queries
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                   Serving Layer                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │            Real-Time Dashboards                               │   │
│  │  • Power BI / Grafana with live data                         │   │
│  │  • REST APIs for trading applications                        │   │
│  │  • Kafka topics for downstream consumers                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Python producer maintains persistent WebSocket connections to Binance API, batches events, and publishes to Event Hub
2. **Buffering**: Event Hub provides durable buffering with partitioning for parallel consumption
3. **Processing**: Spark Structured Streaming reads from Event Hub, applies transformations in micro-batches
4. **Storage**: Data flows through Bronze (raw) → Silver (cleaned) → Gold (aggregated) layers in Delta Lake
5. **Serving**: Analytics applications query Gold layer for real-time insights and historical trends

## State & Processing Logic

### Stateless vs Stateful Processing

**Stateless Processing** (Bronze/Silver layers):
- Each event processed independently without dependency on previous events
- Operations include schema validation, type conversion, and deduplication
- Highly parallelizable and horizontally scalable

**Stateful Processing** (Gold layer):
- Maintains state across events for running aggregations and windowed calculations
- Windowing operations: Tumbling windows for OHLCV (1m, 5m, 15m, 1h), sliding windows for rolling metrics
- Aggregations over time: Volume-weighted average prices (VWAP), cumulative volume, price volatility measures
- Requires checkpointing for fault tolerance and state recovery

### Windowing Strategy

- **Event-Time Windows**: Based on trade timestamps, not processing time
- **Watermarking**: 5-minute watermark delay to handle out-of-order events
- **Allowed Lateness**: Events arriving within watermark window are processed
- **Late Event Handling**: Events beyond watermark are dropped or sent to dead letter queue

## Failure Scenarios & Handling

### API Downtime Handling
- **Connection Resilience**: Automatic reconnection with exponential backoff (1s, 2s, 4s, max 60s)
- **Multiple Connections**: Maintain redundant WebSocket connections per symbol
- **Circuit Breaker**: Suspend connections after 5 consecutive failures, resume with health checks
- **Data Gap Detection**: Alert when no events received for >30 seconds per symbol

### Duplicate Event Handling
- **Event Deduplication**: Use trade_id as unique identifier for deduplication
- **Idempotent Processing**: Delta Lake upsert operations prevent duplicate writes
- **Stateful Deduplication**: Maintain bloom filters in streaming state for high-throughput deduplication

### Late-Arriving Data
- **Watermark Configuration**: 5-minute tolerance for out-of-order events
- **Late Event Processing**: Events within watermark are included in aggregations
- **Compaction Strategy**: Periodic compaction removes outdated window states
- **Audit Logging**: Late events logged for analysis and system tuning

### Pipeline Crash Recovery
- **Checkpointing**: Persistent checkpoints in ADLS Gen2 enable exactly-once processing
- **Automatic Restart**: Databricks job monitoring restarts failed streaming jobs
- **State Recovery**: Streaming state restored from last checkpoint, minimizing data loss
- **Graceful Degradation**: Dead letter queues capture malformed events during recovery

## Design Tradeoffs

### Streaming vs Batch Processing

**Why Streaming**:
- Real-time market signals require immediate processing (<5s latency)
- Batch processing introduces 1-2 hour delays, missing intraday trading opportunities
- Continuous processing enables real-time alerting and automated trading strategies

**Tradeoffs**:
- **Complexity**: Streaming requires state management, watermarking, and fault tolerance
- **Cost**: Continuous compute vs batch scheduling (offset by auto-scaling)
- **Operational Overhead**: 24/7 monitoring vs scheduled batch windows

### Latency vs Cost Optimization

**Latency Requirements**:
- End-to-end <5s processing drives micro-batch intervals and resource allocation
- Photon engine and auto-scaling balance performance with cost efficiency

**Cost Considerations**:
- Auto-scaling from 2-20 workers based on throughput prevents over-provisioning
- Spot instances used for non-critical workloads during off-peak hours
- Event Hub throughput units scale dynamically (1-40 TU) based on ingress rates

### Simplicity vs Scalability

**Scalability Design**:
- Horizontal scaling through Event Hub partitions (32) and Databricks workers (20 max)
- Partitioning strategy enables parallel processing across symbols and time windows
- Delta Lake optimizations (Z-ordering, liquid clustering) support concurrent reads/writes

**Simplicity Tradeoffs**:
- Medallion architecture adds layers but enables data quality and performance isolation
- Structured Streaming chosen over lower-level APIs for operational simplicity
- Managed services (Event Hub, Databricks) reduce infrastructure complexity

## How This Scales in Production

### Horizontal Scaling
- **Event Hub**: 32 partitions enable parallel consumption by multiple Databricks clusters
- **Spark Clusters**: Auto-scaling from 2 to 20 workers based on event throughput and processing lag
- **Delta Lake**: Concurrent reads/writes across multiple consumers without locking

### Auto-Scaling Strategy
- **Throughput-Based Scaling**: Scale up when events/minute exceeds 50K, scale down below 10K
- **Lag-Based Scaling**: Add workers when processing lag exceeds 30 seconds
- **Cost Controls**: Maximum worker limits prevent runaway costs during extreme volatility

### Data Partitioning Strategy
- **Event Hub**: Partitioned by symbol hash to distribute load evenly across partitions
- **Bronze Layer**: `date/hour/symbol` partitioning for ingestion parallelism and efficient time-based queries
- **Silver/Gold Layers**: `date/symbol` with Z-ordering on `timestamp` for optimal query performance
- **Consumer Groups**: Multiple downstream applications can consume independently without interference

## Current Limitations

- **Extreme Spike Handling**: System tested to 200K events/minute; may require manual scaling for black swan events
- **Monitoring Gaps**: Limited distributed tracing across Event Hub → Databricks → Delta Lake pipeline
- **No Full Observability**: Missing end-to-end latency tracking and business metric monitoring
- **Schema Evolution**: Limited support for breaking schema changes without downtime
- **Cross-Region Failover**: Currently single-region deployment; geo-redundancy planned for Q2

## Reliability

### Fault Tolerance

**Checkpointing**:
- Streaming checkpoints stored in ADLS Gen2
- Enables exactly-once processing across failures
- Automatic recovery from last checkpoint

**Exactly-Once Processing**:
- Idempotent writes to Delta Lake
- Event deduplication by trade ID
- Transactional guarantees with Delta Lake

### Failure Handling

**API Failures**:
- Automatic reconnection with exponential backoff
- Multiple WebSocket connections per symbol
- Circuit breaker pattern for persistent failures

**Processing Failures**:
- Spark streaming job restart from checkpoint
- Dead letter queues for malformed events
- Alerting for processing lag > 30 seconds

**Storage Failures**:
- ADLS Gen2 geo-redundant storage
- Delta Lake time travel for data recovery
- Cross-region replication for disaster recovery

## Data Modeling

### Bronze Layer (Raw Streaming Data)

**Purpose**: Immutable capture of all market events
```
{
  "event_type": "trade",
  "symbol": "BTCUSDT",
  "price": "45123.45",
  "quantity": "0.001",
  "trade_id": 123456789,
  "timestamp": 1640995200000,
  "ingestion_ts": "2024-01-27T10:30:15.123Z"
}
```

**Characteristics**:
- Full fidelity preservation
- Schema-on-read approach
- Partitioned for efficient querying
- Audit trail with metadata

### Silver Layer (Cleaned Structured Data)

**Transformations**:
- Type conversions (string prices → decimal)
- Timestamp parsing (milliseconds → datetime)
- Null handling and validation
- Deduplication by trade_id

**Schema**:
```
symbol: string
price: decimal(18,8)
quantity: decimal(18,8)
trade_id: long
event_time: timestamp
ingestion_time: timestamp
buyer_maker: boolean
```

### Gold Layer (Analytics Aggregations)

**Real-Time Aggregations**:
- **OHLCV Windows**: 1m, 5m, 15m, 1h candles
- **Volume Metrics**: VWAP, total volume by symbol
- **Market Indicators**: Price volatility, spread analysis

**Example Gold Table**:
```
symbol: string
window_start: timestamp
window_end: timestamp
open_price: decimal(18,8)
high_price: decimal(18,8)
low_price: decimal(18,8)
close_price: decimal(18,8)
volume: decimal(18,8)
vwap: decimal(18,8)
trade_count: long
```

## Production Considerations

### Monitoring

**Key Metrics**:
- **Processing Lag**: Difference between event time and processing time
- **Throughput**: Events processed per minute/second
- **Error Rate**: Failed events percentage
- **Resource Utilization**: CPU/memory usage across cluster

**Tools**:
- Azure Monitor for infrastructure metrics
- Databricks Job Metrics for streaming performance
- Custom dashboards with Grafana/KQL

### Alerting

**Critical Alerts**:
- Processing lag > 30 seconds
- Error rate > 1%
- Cluster utilization > 90%
- API connection failures

**Notification Channels**:
- Email/SMS for critical issues
- Slack integration for team notifications
- PagerDuty for on-call escalation

### Schema Evolution

**Handling Changes**:
- Delta Lake schema enforcement with evolution
- Backward-compatible changes only
- Migration scripts for breaking changes
- Schema registry for version control

### Cost Optimization

**Compute**:
- Auto-scaling based on throughput
- Spot instances for non-critical workloads
- Photon engine for query acceleration

**Storage**:
- ADLS Gen2 lifecycle policies
- Delta Lake OPTIMIZE for compaction
- Z-ordering for query performance

**Network**:
- Regional data transfers
- Compression for data in transit
- Event Hub capture to reduce egress costs

This platform powers real-time cryptocurrency analytics, enabling traders and analysts to make informed decisions with live market data and historical context.
