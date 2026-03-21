import datetime
from fastapi import HTTPException
import httpx

from app.broker.kis.enums import ORD_DVSN_KRX, EXCG_ID_DVSN_CD
from app.broker.kis.kis_order import KISOrder
from app.core.enums import ORDER_TYPE
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis import OrderResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

class TradeService:
    """
    _summary_
    - 실제 주문 로직을 담당하는 서비스 레이어 클래스.
    
    _description_
    - API 라우터에서는 이 클래스를 호출해서 주문 관련 비즈니스 로직을 처리하도록 구현.
    - 주문 체결 요청에 성공, 실패 보장, 트랜잭션 처리, 주문 유형에 따른 파라미터 변환 등 주문과 관련된 핵심 로직을 담당.
    """
    def __init__(self, kis_order: KISOrder):
        self.kis_order = kis_order
    
    
    # ⚙️ 주문 유형에 따른 API 파라미터 변환 로직을 private method로 관리
    def _resolve_order_params(self, order_type: ORDER_TYPE, price: str) -> tuple[str, str]:
        if order_type == ORDER_TYPE.MARKET:
            return ORD_DVSN_KRX.MARKET.value, "0"
        
        if order_type == ORDER_TYPE.LIMIT:
            if price in ("0", "", None):
                raise HTTPException(status_code=400, detail="지정가 주문은 price 값이 필요합니다.")
            return ORD_DVSN_KRX.LIMIT.value, price
        
        raise HTTPException(status_code=400, detail="order_type market 또는 limit만 가능합니다.")
    
    
    # ⚙️ 국내 주식 현금 매수 체결 요청
    async def buy_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: ORDER_TYPE,
        price: str = "0",
    ) -> OrderResponse:
        # 1. 주문 유형에 의한 파라미터 변환
        order_mode, normalized_price = self._resolve_order_params(order_type, price)
        logger.info(f"매수 서비스 호출 - 종목: {stock_code}, 수량: {quantity}, 주문 유형: {order_type}, 가격: {normalized_price}")
        
        try:
            # 2. KISOrder 클래스의 매수 메서드 호출, 주문 체결 요청
            buy_response =  await self.kis_order.buy_domestic_stock_by_cash(
                access_token=access_token,
                account_no=settings.KIS_ACCOUNT_NO,
                account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
                order_type=order_mode,
                stock_code=stock_code,
                quantity=quantity,
                price=normalized_price,
                exchange_type=EXCG_ID_DVSN_CD.KRX.value,
            )
            
            today = datetime.datetime.now()
            order_datetime = today.replace(hour=int(buy_response.output.ORD_TMD[:2]), minute=int(buy_response.output.ORD_TMD[2:4]), second=int(buy_response.output.ORD_TMD[4:6]))
            logger.info(f"매수 체결 성공 - 주문 번호: {buy_response.output.ODNO}, 주문 시간 : {order_datetime}, KRX 전송주문번호 : {buy_response.output.KRX_FWDG_ORD_ORGNO}")
            
            return buy_response
        
        # ❌ 재시도 대상 (네트워크 계열)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.error(f"주문 실패 (네트워크 오류): {e}")
            raise HTTPException(
                status_code=503,
                detail="매수 체결 요청 중 네트워크 오류가 발생했습니다."
            )
        
        # ❌ 주문 거절 (브로커에서 올라온 에러)
        except KISOrderError as e:
            logger.error(f"주문 실패 (거절): {e}")
            raise HTTPException(
                status_code=400,
                detail=e.message
            )
        
        # ❌ 기타 예외
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="매수 주문 처리 중 오류 발생"
            )

        # TODO: 실제 운영에서는 네트워크 오류, 브로커 거절 등 다양한 실패 시나리오에 대비한 재시도 로직과 예외 처리를 구현하는 것이 좋음. 아래는 간단한 예시 코드.
        # max_retry = 3
        # delay = 0.5
        
        # for attempt in range(max_retry):
        #     try:
        #         # 2. KISOrder 클래스의 매수 메서드 호출, 주문 체결 요청
        #         order_response =  await self.kis_order.buy_domestic_stock_by_cash(
        #             access_token=access_token,
        #             account_no=settings.KIS_ACCOUNT_NO,
        #             account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        #             order_type=order_mode,
        #             stock_code=stock_code,
        #             quantity=quantity,
        #             price=normalized_price,
        #             exchange_type=EXCG_ID_DVSN_CD.KRX.value,
        #         )
                
        #         today = datetime.datetime.now()
        #         order_datetime = today.replace(hour=int(order_response.output.ORD_TMD[:2]), minute=int(order_response.output.ORD_TMD[2:4]), second=int(order_response.output.ORD_TMD[4:6]))
        #         logger.info(f"매수 체결 성공 - 주문 번호: {order_response.output.ODNO}, 주문 시간 : {order_datetime}, KRX 전송주문번호 : {order_response.output.KRX_FWDG_ORD_ORGNO}")
            
        #         return order_response
            
        #     # ❌ 재시도 대상 (네트워크 계열)
        #     except (httpx.HTTPError, httpx.TimeoutException) as e:
        #         logger.warning(f"[{attempt+1}/{max_retry}] 네트워크 오류: {e}")
        #         if attempt == max_retry - 1:
        #             logger.error("재시도 실패 - 주문 불확실 상태")
        #             raise HTTPException(
        #                 status_code=500,
        #                 detail="주문 요청 실패 (네트워크 오류)"
        #             )
        #         await asyncio.sleep(delay * (attempt + 1))
            
        #     # ❌ 주문 거절 (브로커에서 올라온 에러)
        #     except KISOrderError as e:
        #         logger.error(f"주문 실패 (거절): {e}")
        #         raise HTTPException(
        #             status_code=400,
        #             detail=e.message
        #         )
            
        #     # ❌ 기타 예외
        #     except Exception as e:
        #         logger.error(f"예상치 못한 오류: {e}")
        #         raise HTTPException(
        #             status_code=500,
        #             detail="매수 주문 처리 중 오류 발생"
        #         )
    
    
    # ⚙️ 국내 주식 현금 매도 체결 요청
    async def sell_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: ORDER_TYPE,
        price: str = "0",
    ) -> OrderResponse:
        # 1. 주문 유형에 의한 파라미터 변환
        order_mode, normalized_price = self._resolve_order_params(order_type, price)
        logger.info(f"매도 서비스 호출 - 종목: {stock_code}, 수량: {quantity}, 주문 유형: {order_type}, 가격: {normalized_price}")
        
        try:
            # 2. KISOrder 클래스의 매도 메서드 호출, 주문 체결 요청
            sell_response = await self.kis_order.sell_domestic_stock_by_cash(
                access_token=access_token,
                account_no=settings.KIS_ACCOUNT_NO,
                account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
                order_type=order_mode,
                stock_code=stock_code,
                quantity=quantity,
                price=normalized_price,
                exchange_type=EXCG_ID_DVSN_CD.KRX.value,
            )
            
            today = datetime.datetime.now()
            order_datetime = today.replace(hour=int(sell_response.output.ORD_TMD[:2]), minute=int(sell_response.output.ORD_TMD[2:4]), second=int(sell_response.output.ORD_TMD[4:6]))
            logger.info(f"매도 체결 성공 - 주문 번호: {sell_response.output.ODNO}, 주문 시간 : {order_datetime}, KRX 전송주문번호 : {sell_response.output.KRX_FWDG_ORD_ORGNO}")
        
            return sell_response
        
        # ❌ 재시도 대상 (네트워크 계열)
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.error(f"주문 실패 (네트워크 오류): {e}")
            raise HTTPException(
                status_code=503,
                detail="매도 체결 요청 중 네트워크 오류가 발생했습니다."
            )
            
        # ❌ 주문 거절 (브로커에서 올라온 에러)
        except KISOrderError as e:
            logger.error(f"주문 실패 (거절): {e}")
            raise HTTPException(
                status_code=400,
                detail=e.message
            )
        
        # ❌ 기타 예외
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")
            raise HTTPException(
                status_code=500,
                detail="매도 주문 처리 중 오류 발생"
            )