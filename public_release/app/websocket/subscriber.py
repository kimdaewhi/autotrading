import asyncio
import json
import redis.asyncio as redis

from app.core.settings import settings
from app.utils.logger import get_logger
from app.websocket.manager import ws_manager

logger = get_logger(__name__)

ORDER_WS_CHANNEL = "order_updates"


# ⚙️ Redis Pub/Sub 채널로 주문 이벤트 구독 및 웹소켓 클라이언트로 브로드캐스트
async def subscribe_order_events() -> None:
    redis_client = redis.from_url(
        settings.CELERY_BROKER_URL,
        decode_responses=True,
    )
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(ORDER_WS_CHANNEL)
        logger.info(f"주문 웹소켓 Pub/Sub 구독 시작. channel={ORDER_WS_CHANNEL}")
        
        # Redis Pub/Sub 메시지 수신 루프
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            
            if not message:
                await asyncio.sleep(0.1)
                continue
            
            # Redis Pub/Sub 메시지 처리
            try:
                raw_data = message["data"]
                payload = json.loads(raw_data)
                
                event_type = payload.get("type")
                event_data = payload.get("data")
                
                if event_type == "order_updated":
                    # logger.info(f"[SUBSCRIBER-RECV] order_updated")
                    await ws_manager.broadcast_order_updated(event_data)
                    # logger.info(f"[SUBSCRIBER-BROADCAST] order_updated done")
                elif event_type == "order_created":
                    # logger.info(f"[SUBSCRIBER-RECV] order_created")
                    await ws_manager.broadcast_order_created(event_data)
                    # logger.info(f"[SUBSCRIBER-BROADCAST] order_created done")
                else:
                    logger.warning(f"알 수 없는 주문 이벤트 타입: {event_type}")
                
            except Exception as e:
                logger.error(f"주문 Pub/Sub 메시지 처리 실패: {e}")
    except asyncio.CancelledError:
        logger.info("주문 웹소켓 Pub/Sub 구독 종료")
        raise
    finally:
        await pubsub.unsubscribe(ORDER_WS_CHANNEL)
        await pubsub.close()
        await redis_client.close()