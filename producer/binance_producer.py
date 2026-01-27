import asyncio
import json
import logging
from datetime import datetime, UTC
from typing import List, Dict, Any
import websockets
from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient
from config import EVENT_HUB_CONNECTION_STR, EVENT_HUB_NAME

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("azure").setLevel(logging.WARNING)

BINANCE_WS_BASE = "wss://stream.binance.com:9443/stream"
SYMBOLS = ["btcusdt", "ethusdt", "bnbusdt", "solusdt", "adausdt"]
STREAM_TYPES = ["trade"]
BATCH_SIZE = 10
BATCH_TIMEOUT = 5

class BinanceStreamer:
    
    def __init__(self, symbols: List[str], stream_types: List[str]):
        self.symbols = symbols
        self.stream_types = stream_types
        self.ws_url = self._build_websocket_url()
        self.event_queue = asyncio.Queue()
        self.is_running = False
        
    def _build_websocket_url(self) -> str:
        streams = []
        for symbol in self.symbols:
            for stream_type in self.stream_types:
                streams.append(f"{symbol}@{stream_type}")
        
        streams_param = "/".join(streams)
        url = f"{BINANCE_WS_BASE}?streams={streams_param}"
        logger.info(f"WebSocket URL: {url}")
        return url
    
    async def connect_and_stream(self):
        retry_delay = 1
        max_retry_delay = 60
        
        while self.is_running:
            try:
                logger.info("Connecting to Binance WebSocket...")
                async with websockets.connect(self.ws_url) as websocket:
                    logger.info("Connected to Binance WebSocket successfully!")
                    retry_delay = 1
                    
                    while self.is_running:
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(), 
                                timeout=30
                            )
                            
                            data = json.loads(message)
                            enriched_data = self._enrich_event(data)
                            await self.event_queue.put(enriched_data)
                            
                        except asyncio.TimeoutError:
                            logger.debug("Sending ping to keep connection alive")
                            await websocket.ping()
                            
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"WebSocket error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in WebSocket connection: {e}")
            
            if self.is_running:
                logger.info(f"Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
    
    def _enrich_event(self, data: Dict[str, Any]) -> Dict[str, Any]:
        stream_data = data.get("data", {})
        
        enriched = {
            "source": "binance",
            "stream": data.get("stream", "unknown"),
            "ingestion_timestamp": datetime.now(UTC).isoformat(),
            "event_type": stream_data.get("e", "unknown"),
            "event_time": stream_data.get("E", 0),
            "symbol": stream_data.get("s", "unknown"),
            "trade_data": {
                "event_type": stream_data.get("e"),
                "event_time_ms": stream_data.get("E"),
                "symbol": stream_data.get("s"),
                "trade_id": stream_data.get("t"),
                "price": stream_data.get("p"),
                "quantity": stream_data.get("q"),
                "buyer_order_id": stream_data.get("b"),
                "seller_order_id": stream_data.get("a"),
                "trade_time": stream_data.get("T"),
                "is_buyer_maker": stream_data.get("m"),
                "is_best_match": stream_data.get("M"),
                "price_change_percent": stream_data.get("P"),
                "close_price": stream_data.get("c"),
                "open_price": stream_data.get("o"),
                "high_price": stream_data.get("h"),
                "low_price": stream_data.get("l"),
                "volume": stream_data.get("v")
            }
        }
        
        return enriched
    
    async def start(self):
        self.is_running = True
        await self.connect_and_stream()
    
    def stop(self):
        self.is_running = False

class EventHubProducer:
    
    def __init__(self, connection_str: str, eventhub_name: str):
        self.connection_str = connection_str
        self.eventhub_name = eventhub_name
        self.producer = None
        self.events_sent = 0
        self.errors = 0
        
    async def initialize(self):
        self.producer = EventHubProducerClient.from_connection_string(
            conn_str=self.connection_str,
            eventhub_name=self.eventhub_name
        )
        await self.producer.__aenter__()
        logger.info("Event Hub producer initialized and connected")
    
    async def send_batch(self, events: List[Dict[str, Any]]):
        if not events:
            return
        
        try:
            event_data_batch = await self.producer.create_batch()
            
            events_added = 0
            for event in events:
                try:
                    event_json = json.dumps(event)
                    event_data = EventData(event_json)
                    event_data_batch.add(event_data)
                    events_added += 1
                    
                except ValueError:
                    await self.producer.send_batch(event_data_batch)
                    self.events_sent += events_added
                    logger.info(f"Sent full batch of {events_added} events (Total: {self.events_sent})")
                    
                    event_data_batch = await self.producer.create_batch()
                    event_data_batch.add(event_data)
                    events_added = 1
            
            if len(event_data_batch) > 0:
                await self.producer.send_batch(event_data_batch)
                self.events_sent += events_added
                logger.info(f"✅ Sent batch of {events_added} events (Total: {self.events_sent})")
                
        except Exception as e:
            self.errors += 1
            logger.error(f"❌ ERROR sending batch to Event Hub: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def close(self):
        if self.producer:
            await self.producer.__aexit__(None, None, None)
            logger.info(f"Producer closed. Total events sent: {self.events_sent}, Errors: {self.errors}")

async def batch_processor(
    event_queue: asyncio.Queue,
    event_hub_producer: EventHubProducer,
    batch_size: int,
    batch_timeout: float
):
    batch = []
    last_send_time = asyncio.get_event_loop().time()
    
    while True:
        try:
            event = await asyncio.wait_for(
                event_queue.get(),
                timeout=1.0
            )
            batch.append(event)
            
            current_time = asyncio.get_event_loop().time()
            time_since_last_send = current_time - last_send_time
            
            if len(batch) >= batch_size or time_since_last_send >= batch_timeout:
                await event_hub_producer.send_batch(batch)
                batch = []
                last_send_time = current_time
                
        except asyncio.TimeoutError:
            if batch:
                current_time = asyncio.get_event_loop().time()
                time_since_last_send = current_time - last_send_time
                
                if time_since_last_send >= batch_timeout:
                    await event_hub_producer.send_batch(batch)
                    batch = []
                    last_send_time = current_time
                    
        except Exception as e:
            logger.error(f"Error in batch processor: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await asyncio.sleep(1)

async def run():
    logger.info("=" * 80)
    logger.info("Starting Binance to Event Hub Streaming Producer")
    logger.info("=" * 80)
    logger.info(f"Monitoring symbols: {SYMBOLS}")
    logger.info(f"Stream types: {STREAM_TYPES}")
    logger.info(f"Event Hub: {EVENT_HUB_NAME}")
    logger.info("=" * 80)
    
    streamer = BinanceStreamer(SYMBOLS, STREAM_TYPES)
    producer = EventHubProducer(EVENT_HUB_CONNECTION_STR, EVENT_HUB_NAME)
    
    try:
        await producer.initialize()
        
        streamer_task = asyncio.create_task(streamer.start())
        processor_task = asyncio.create_task(
            batch_processor(
                streamer.event_queue,
                producer,
                BATCH_SIZE,
                BATCH_TIMEOUT
            )
        )
        
        await asyncio.gather(streamer_task, processor_task)
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        streamer.stop()
        await producer.close()
        logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(run())