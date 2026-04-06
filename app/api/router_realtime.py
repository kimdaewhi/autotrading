# app/api/routes/realtime.py
from fastapi import APIRouter, Request

from app.market.realtime.kis_realtime_client import KISRealtimeClient

router = APIRouter(prefix="/realtime", tags=["realtime"])



# ⚙️ 실시간 시세 구독 API
@router.post("/subscribe/{stock_code}")
async def subscribe(stock_code: str, request: Request):
    client: KISRealtimeClient = request.app.state.realtime_client
    await client.subscribe(stock_code)
    return {"message": f"{stock_code} 구독 시작"}


# ⚙️ 실시간 시세 구독 해제 API
@router.post("/unsubscribe/{stock_code}")
async def unsubscribe(stock_code: str, request: Request):
    client: KISRealtimeClient = request.app.state.realtime_client
    await client.unsubscribe(stock_code)
    return {"message": f"{stock_code} 구독 해제"}


# ⚙️ 현재 구독 중인 종목 조회 API
@router.get("/subscriptions")
async def get_subscriptions(request: Request):
    client: KISRealtimeClient = request.app.state.realtime_client
    return {"subscribed_codes": list(client._subscribed_codes)}