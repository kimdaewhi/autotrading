from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.core.enums import ORDER_ACTION, ORDER_KIND, ORDER_TYPE, ORDER_STATUS
from app.broker.kis.enums import CCDL_DVSN_CD, EXCG_ID_DVSN_CD, SLL_BUY_DVSN_CD
from app.db.models.order import Order
from app.utils.logger import get_logger

from app.broker.kis.kis_order import KISOrder
from app.services.trade_service import TradeService
from app.schemas.kis import DailyOrderExecutionResponse, OrderResponse

from app.db.session import get_db
from app.repository.order_repository import create_order, get_order_by_id
from app.worker.tasks_order import process_order


logger = get_logger(__name__)

security = HTTPBearer()
router = APIRouter()

def get_kis_order() -> KISOrder:
    return KISOrder(
        appkey=settings.KIS_APP_KEY,
        appsecret=settings.KIS_APP_SECRET,
        url=f"{settings.kis_base_url}",
    )

def get_trade_service(kis_order: KISOrder = Depends(get_kis_order)) -> TradeService:
    return TradeService(kis_order=kis_order)


# ⚙️ 주문 관련 입력값 검증 로직을 private method로 관리 (주문 유형별로 price 필수 여부 등)
def validate_order_request(
    stock_code: str,
    quantity: int,
    order_type: ORDER_TYPE,
    price: Decimal,
) -> None:
    if not stock_code.isdigit() or len(stock_code) != 6:
        raise HTTPException(status_code=400, detail="stock_code는 6자리 숫자여야 합니다.")
    
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity는 1 이상이어야 합니다.")
    
    if order_type == ORDER_TYPE.MARKET:
        if price != Decimal("0"):
            raise HTTPException(status_code=400, detail="시장가 주문은 price가 0이어야 합니다.")
        return
    
    if order_type == ORDER_TYPE.LIMIT:
        if price <= Decimal("0"):
            raise HTTPException(status_code=400, detail="지정가 주문은 price가 0보다 커야 합니다.")
        return
    
    raise HTTPException(status_code=400, detail="지원하지 않는 order_type 입니다.")


# ⚙️ 주문 취소 입력값 검증
def validate_cancel_request(
    order_id: str,
    quantity: int,
) -> None:
    if not str(order_id).strip():
        raise HTTPException(status_code=400, detail="order_id는 필수입니다.")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="취소 수량은 1 이상이어야 합니다.")


# ⚙️ 주문 정정 입력값 검증
def validate_revise_request(
    order_id: str,
    quantity: int,
    order_type: ORDER_TYPE,
    price: Decimal,
) -> None:
    if not str(order_id).strip():
        raise HTTPException(status_code=400, detail="order_no는 필수입니다.")
    
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="정정 수량은 1 이상이어야 합니다.")
    
    if order_type == ORDER_TYPE.MARKET:
        if price != Decimal("0"):
            raise HTTPException(status_code=400, detail="시장가 정정은 price가 0이어야 합니다.")
        return
    
    if order_type == ORDER_TYPE.LIMIT:
        if price <= Decimal("0"):
            raise HTTPException(status_code=400, detail="지정가 정정은 price가 0보다 커야 합니다.")
        return
    
    raise HTTPException(status_code=400, detail="지원하지 않는 order_type 입니다.")


# ⚙️ 원주문에 대한 정정/취소 가능 여부 검증
def validate_original_order_for_modify_cancel(original_order: Order | None) -> Order:
    if original_order is None:
        raise HTTPException(status_code=404, detail="원주문을 찾을 수 없습니다.")
    
    if original_order.order_kind not in {ORDER_KIND.NEW.value, ORDER_KIND.MODIFY.value}:
        raise HTTPException(
            status_code=400,
            detail="원주문은 신규 주문(NEW) 또는 정정 주문(MODIFY)만 가능합니다.",
        )
        
    if original_order.status not in {ORDER_STATUS.ACCEPTED.value, ORDER_STATUS.PARTIAL_FILLED.value}:
        raise HTTPException(
            status_code=400,
            detail="접수 또는 부분체결 상태의 주문만 정정/취소할 수 있습니다.",
        )
        
    if not original_order.broker_order_no or not original_order.broker_org_no:
        raise HTTPException(
            status_code=400,
            detail="브로커 주문번호가 없는 주문은 정정/취소할 수 없습니다.",
        )
    
    if int(original_order.remaining_qty or 0) <= 0:
        raise HTTPException(
            status_code=400,
            detail="잔여 수량이 없는 주문은 정정/취소할 수 없습니다.",
        )
    
    return original_order


# ⚙️ 국내주식 현금 매수 체결 요청
@router.post("/domestic-stock/buy")
async def buy_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: int = Query(default=0, description="주문 수량"),
    order_type: ORDER_TYPE = Query(default=ORDER_TYPE.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: Decimal = Query(default=Decimal("0"), description="시장가 주문인 경우 0으로 설정"),
    db: AsyncSession = Depends(get_db),
) -> None:
    # 입력값 검증
    validate_order_request(
        stock_code=stock_code,
        quantity=quantity,
        order_type=order_type,
        price=price,
    )
    
    # # TODO: 일단은 KOSPI(KRX) 만 고려해서 order_type 설정하도록. 추후에 종목 코드에 따른 거래소 구분 로직 추가 필요.
    # 1. 매수 체결 요청 레코드 생성 및 DB 저장
    logger.info(f"매수 주문 생성 및 DB 저장 시작")
    order = await create_order(
        db=db,
        order_data = {
            "account_no": settings.KIS_ACCOUNT_NO,
            "account_product_code": settings.KIS_ACCOUNT_PRODUCT_CODE,
            
            "market": EXCG_ID_DVSN_CD.KRX.value,
            "stock_code": stock_code,
            "order_pos": ORDER_ACTION.BUY.value,
            "order_kind": ORDER_KIND.NEW.value,
            "order_type": order_type.value,
            
            "order_price": Decimal(price),
            "order_qty": int(quantity),
            "remaining_qty": int(quantity),
            
            "status": ORDER_STATUS.PENDING.value,
        }
    )
    
    await db.commit()
    
    # 2. commit 이후 큐에 주문 처리 태스크 등록
    process_order.delay(str(order.id))
    logger.info(f"매수 주문 생성 및 큐 적재 완료 : 주문 ID : {order.id}")
    
    return {
        "order_id": str(order.id),
        "status": order.status,
        "message": "매수 주문 요청이 접수되었습니다."
    }


# ⚙️ 국내 주식 현금 매도 체결 요청
@router.post("/domestic-stock/sell")
async def sell_domestic_stock(
    stock_code: str = Query(..., description="종목 코드 (예: 삼성전자 005930)"),
    quantity: int = Query(default=0, description="주문 수량"),
    order_type: ORDER_TYPE = Query(default=ORDER_TYPE.MARKET, description="주문 유형 (시장가: market, 지정가: limit)"),
    price: Decimal = Query(default=Decimal("0"), description="시장가 주문인 경우 0으로 설정"),
    db: AsyncSession = Depends(get_db),
) -> None:
    # 입력값 검증
    validate_order_request(
        stock_code=stock_code,
        quantity=quantity,
        order_type=order_type,
        price=price,
    )
    
    # 1. 매도 체결 요청 레코드 생성 및 DB 저장
    logger.info(f"매도 주문 생성 및 DB 저장 시작")
    
    order = await create_order(
        db=db,
        order_data={
            "account_no": settings.KIS_ACCOUNT_NO,
            "account_product_code": settings.KIS_ACCOUNT_PRODUCT_CODE,
            
            "market": EXCG_ID_DVSN_CD.KRX.value,
            "stock_code": stock_code,
            "order_pos": ORDER_ACTION.SELL.value,
            "order_kind": ORDER_KIND.NEW.value,
            "order_type": order_type.value,
            "order_price": Decimal(price),
            "order_qty": int(quantity),
            "remaining_qty": int(quantity),
            
            "status": ORDER_STATUS.PENDING.value,
        },
    )
    await db.commit()
    
    # 2. commit 이후 큐에 주문 처리 태스크 등록
    process_order.delay(str(order.id))
    logger.info(f"매도 주문 생성 및 큐 적재 완료 : 주문 ID : {order.id}")
    
    return {
        "order_id": str(order.id),
        "status": order.status,
        "message": "매도 주문 요청이 접수되었습니다."
    }


# ⚙️ 국내주식 주문 취소 요청
@router.post("/domestic-stock/cancel")
async def cancel_domestic_stock_order(
    order_id: str = Query(..., description="주문 ID(한투 원주문번호가 아닌 DB 레코드 기준 주문 ID)"),
    quantity: int = Query(default=0, description="취소 수량"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 입력값 검증
    validate_cancel_request(
        order_id=order_id,
        quantity=quantity,
    )
    
    # 1. 원주문 조회 및 취소 가능 여부 검증
    original_order = await get_order_by_id(db=db, order_id=order_id)
    if not original_order:
        raise HTTPException(status_code=404, detail=f"주문ID를 찾을 수 없습니다. order_id: {order_id}")
    # 취소/정정 가능한 주문인지 검증(실패/취소/완료된 주문은 정정/취소 불가)
    validate_original_order_for_modify_cancel(original_order)
    
    # 원주문의 남은 수량과 취소 요청 수량을 비교해서 전체취소/부분취소 인지 판단
    cancel_qty = original_order.remaining_qty if original_order.remaining_qty == quantity else int(quantity)
    
    order = await create_order(
        db=db,
        order_data={
            "account_no": original_order.account_no,
            "account_product_code": original_order.account_product_code,
            "market": original_order.market,
            "stock_code": original_order.stock_code,
            "order_pos": original_order.order_pos,
            "order_kind": ORDER_KIND.CANCEL.value,
            "order_type": original_order.order_type,
            "order_price": None,
            "order_qty": cancel_qty,
            "remaining_qty": cancel_qty,
            "status": ORDER_STATUS.PENDING.value,
            "original_order_id": original_order.id,
            "original_broker_order_no": original_order.broker_order_no,
            "original_broker_org_no": original_order.broker_org_no,
        },
    )
    await db.commit()
    
    process_order.delay(str(order.id))
    logger.info(f"취소 주문 생성 및 큐 적재 완료 : 주문 ID : {order.id}, 원주문번호 : {order_id}")
    
    return {
        "order_id": str(order.id),
        "status": order.status,
        "message": "취소 주문 요청이 접수되었습니다.",
    }


# ⚙️ 국내주식 주문 정정 요청
@router.post("/domestic-stock/revise")
async def revise_domestic_stock_order(
    order_no: str = Query(..., description="주문 ID(한투 원주문번호가 아닌 DB 레코드 기준 주문 ID)"),
    quantity: int = Query(default=0, description="정정 수량"),
    order_type: ORDER_TYPE = Query(..., description="정정 주문 유형"),
    price: Decimal = Query(default=Decimal("0"), description="정정 가격"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    validate_revise_request(
        order_id=order_no,
        quantity=quantity,
        order_type=order_type,
        price=price,
    )
    # 1. 원주문 조회 및 정정 가능 여부 검증
    original_order = await get_order_by_id(db=db, order_id=order_no)
    if not original_order:
        raise HTTPException(status_code=404, detail="원주문을 찾을 수 없습니다.")
    
    # 정정 가능한 주문인지 검증(실패/취소/완료된 주문은 정정/취소 불가)
    validate_original_order_for_modify_cancel(original_order)
    
    # 원주문의 남은 수량과 정정 요청 수량을 비교해서 전체정정/부분정정 인지 판단
    revise_qty = original_order.remaining_qty if original_order.remaining_qty == quantity else int(quantity)
    
    order = await create_order(
        db=db,
        order_data={
            "account_no": original_order.account_no,
            "account_product_code": original_order.account_product_code,
            "market": original_order.market,
            "stock_code": original_order.stock_code,
            
            "order_pos": original_order.order_pos,
            "order_kind": ORDER_KIND.MODIFY.value,
            "order_type": order_type.value,
            "order_price": None if order_type == ORDER_TYPE.MARKET else Decimal(price),
            "order_qty": revise_qty,
            "remaining_qty": revise_qty,
            
            "status": ORDER_STATUS.PENDING.value,
            "original_order_id": original_order.id,
            "original_broker_order_no": original_order.broker_order_no,
            "original_broker_org_no": original_order.broker_org_no
        },
    )
    await db.commit()
    
    process_order.delay(str(order.id))
    logger.info(f"정정 주문 생성 및 큐 적재 완료 : 주문 ID : {order.id}, 원주문번호 : {order_no}")
    
    return {
        "order_id": str(order.id),
        "status": order.status,
        "message": "정정 주문 요청이 접수되었습니다.",
    }


# ⚙️ 국내 주식 일별 주문 체결 조회 요청
@router.get("/domestic-stock/daily-order-executions", response_model=DailyOrderExecutionResponse)
async def get_daily_order_executions(
    start_date: str = Query(..., description="조회 시작일자  (YYYYMMDD)"),
    end_date: str = Query(..., description="조회 종료일자 (YYYYMMDD)"),
    sell_buy_div: SLL_BUY_DVSN_CD = Query(default=SLL_BUY_DVSN_CD.ALL, description="매도/매수 구분 (전체: all, 매도: sell, 매수: buy)"),
    stock_code: str = Query(default="", description="종목 코드"),
    broker_org_no: str = Query(default="", description="주문채번지점번호"),
    broker_order_no: str = Query(default="", description="주문번호"),
    ccld_div: CCDL_DVSN_CD = Query(default=CCDL_DVSN_CD.ALL, description="체결구분"),
    exchange_type: EXCG_ID_DVSN_CD = Query(default=EXCG_ID_DVSN_CD.KRX, description="거래소 구분 (KRX: 코스피/코스닥, KOSDAQ: 코스닥)"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    trade_service: TradeService = Depends(get_trade_service),
) -> DailyOrderExecutionResponse:
    # 1. 인증 정보에서 액세스 토큰 추출
    access_token = credentials.credentials
    
    # 2. 서비스 레이어를 통해 일별 주문 체결 조회 요청
    daily_order_execution_response = await trade_service.get_daily_order_executions(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        sell_buy_div=sell_buy_div,
        stock_code=stock_code,
        broker_org_no=broker_org_no,
        broker_order_no=broker_order_no,
        ccld_div=ccld_div,
        exchange_type=exchange_type,
    )
    
    return daily_order_execution_response