import datetime
from decimal import Decimal

from app.broker.kis.enums import CCDL_DVSN_CD, ORD_DVSN_KRX, EXCG_ID_DVSN_CD, SLL_BUY_DVSN_CD
from app.broker.kis.kis_order import KISOrder
from app.core.enums import ORDER_TYPE
from app.core.exceptions import KISOrderError
from app.core.settings import settings
from app.schemas.kis.kis import DailyOrderExecutionResponse, ModifiableOrdersResponse, OrderResponse
from app.services.safety.kill_switch_service import KillSwitchService
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
    def __init__(self, kis_order: KISOrder, kill_switch_service: KillSwitchService) -> None:
        self.kis_order = kis_order,
        self.kill_switch_service = kill_switch_service
    
    
    # ⚙️ 종목 코드 검증 로직을 private method로 관리 (6자리 숫자 형식 등)
    def _validate_stock_code(self, stock_code: str) -> None:
        code = str(stock_code).strip()
        if not code or not code.isdigit() or len(code) != 6:
            raise ValueError("stock_code는 6자리 숫자여야 합니다.")
    
    
    # ⚙️ 주문 관련 입력값 검증 로직을 private method로 관리 (주문 유형별로 price 필수 여부 등)
    def _validate_order_inputs(
        self,
        stock_code: str,
        order_type: ORDER_TYPE,
        price=None,
    ) -> None:
        self._validate_stock_code(stock_code)
        # 시장가인 경우에는 그냥 price 무시하도록, 지정가는 price 필수로 검증하도록
        if order_type == ORDER_TYPE.MARKET:
            return
        
        if order_type == ORDER_TYPE.LIMIT:
            if price in (None, "", 0, "0"):
                raise ValueError("지정가 주문은 price가 필요합니다.")
            return
        raise ValueError("지원하지 않는 order_type 입니다.")
    
    
    # ⚙️ 주문 유형에 따른 API 파라미터 변환 로직을 private method로 관리
    def _resolve_order_params(
        self,
        order_type: ORDER_TYPE,
        price: str | int | float | Decimal | None,
    ) -> tuple[str, str | int | float | Decimal | None]:
        if order_type == ORDER_TYPE.MARKET:
            return ORD_DVSN_KRX.MARKET.value, "0"
        
        # 여기선 검증하지 말고 단순 변환만
        return ORD_DVSN_KRX.LIMIT.value, price
    
    
    # ⚙️ 주문 취소/정정 API 호출 시 필요한 입력값 검증 로직을 private method로 관리 (원주문번호 필수, 전체취소/일부취소에 따른 quantity 필수 여부 등)
    def _validate_original_order_no(self, order_no: str) -> None:
        if not str(order_no).strip():
            raise ValueError("order_no는 필수입니다.")
    
    
    # ⚙️ 주문 취소/정정 API 호출 시 필요한 입력값 검증 로직을 private method로 관리 (원주문번호 필수, 전체취소/일부취소에 따른 quantity 필수 여부 등)
    def _validate_qty_all_order_yn(self, qty_all_order_yn: str) -> None:
        if qty_all_order_yn not in ("Y", "N"):
            raise ValueError("qty_all_order_yn은 'Y' 또는 'N' 이어야 합니다.")
    
    
    # ⚙️ 주문 취소 API 호출 시 필요한 입력값 검증 로직을 private method로 관리 (원주문번호 필수, 전체취소/일부취소에 따른 quantity 필수 여부 등)
    def _validate_cancel_inputs(
        self,
        order_no: str,
        quantity: str,
        qty_all_order_yn: str,
    ) -> None:
        self._validate_original_order_no(order_no)
        self._validate_qty_all_order_yn(qty_all_order_yn)
        
        if qty_all_order_yn == "N":
            if quantity in (None, "", "0", 0):
                raise ValueError("일부취소는 quantity가 필요합니다.")
    
    
    # ⚙️ 주문 정정 API 호출 시 필요한 입력값 검증 로직을 private method로 관리 (원주문번호 필수, 전체취소/일부취소에 따른 quantity 필수 여부 등)
    def _validate_revise_inputs(
        self,
        order_no: str,
        quantity: str,
        order_type: ORDER_TYPE,
        price,
        qty_all_order_yn: str,
    ) -> None:
        self._validate_original_order_no(order_no)
        self._validate_qty_all_order_yn(qty_all_order_yn)
        
        if qty_all_order_yn == "N":
            if quantity in (None, "", "0", 0):
                raise ValueError("일부정정은 quantity가 필요합니다.")
        
        if order_type == ORDER_TYPE.LIMIT:
            if price in (None, "", "0", 0):
                raise ValueError("지정가 정정은 price가 필요합니다.")
            return
        
        if order_type == ORDER_TYPE.MARKET:
            return
        raise ValueError("지원하지 않는 order_type 입니다.")
    
    
    
    # ⚙️ 국내 주식 현금 매수 체결 요청
    async def buy_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: ORDER_TYPE,
        price: str = "0",
    ) -> OrderResponse:
        
        # 입력값 검증
        self._validate_order_inputs(
            stock_code=stock_code,
            order_type=order_type,
            price=price,
        )
        # 1. 주문 유형에 의한 파라미터 변환
        order_mode, normalized_price = self._resolve_order_params(order_type, price)
        logger.info(f"매수 서비스 호출 - 종목: {stock_code}, 수량: {quantity}, 주문 유형: {order_mode}, 가격: {normalized_price}")
        
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
            logger.info(f"매수 주문 접수 성공 - 주문 번호: {buy_response.output.ODNO}, 주문 시간 : {order_datetime}, KRX 전송주문번호 : {buy_response.output.KRX_FWDG_ORD_ORGNO}")
            
            return buy_response
        except KISOrderError:
            logger.error("매수 주문 실패 (브로커/네트워크)")
            raise
        except Exception as e:
            logger.error(f"매수 주문 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ 국내 주식 현금 매도 체결 요청
    async def sell_domestic_stock(
        self,
        access_token: str,
        stock_code: str,
        quantity: str,
        order_type: ORDER_TYPE,
        price: str = "0",
    ) -> OrderResponse:
        
        # 입력값 검증
        self._validate_order_inputs(
            stock_code=stock_code,
            order_type=order_type,
            price=price,
        )
        
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
            logger.info(f"매도 주문 접수 성공 - 주문 번호: {sell_response.output.ODNO}, 주문 시간 : {order_datetime}, KRX 전송주문번호 : {sell_response.output.KRX_FWDG_ORD_ORGNO}")
        
            return sell_response
        except KISOrderError:
            logger.error("매도 주문 실패 (브로커/네트워크)")
            raise
        except Exception as e:
            logger.error(f"매도 주문 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ 국내 주식 일별 주문 체결 조회
    async def get_daily_order_executions(
        self,
        account_no: str,
        account_product_code: str,
        access_token: str,
        start_date: str,
        end_date: str,
        sell_buy_div: str = SLL_BUY_DVSN_CD.ALL.value,
        stock_code: str = "",
        broker_org_no: str = "",
        broker_order_no: str = "",
        ccld_div: str = CCDL_DVSN_CD.ALL.value,
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
    ) -> DailyOrderExecutionResponse:
        try:
            daily_execution_response = await self.kis_order.get_daily_order_executions(
                access_token=access_token,
                account_no=account_no,
                account_product_code=account_product_code,
                start_date=start_date,
                end_date=end_date,
                sell_buy_div=sell_buy_div,
                stock_code=stock_code,
                broker_org_no=broker_org_no,
                broker_order_no=broker_order_no,
                ccld_div=ccld_div,
                exchange_type=exchange_type,
            )
            
            logger.info(
                f"주식 일별 주문 체결 조회 성공 - 조회 기간 : {start_date} ~ {end_date}, "
                f"매도/매수 구분 : {sell_buy_div}, 종목 코드 : {stock_code}, "
                f"주문채번지점번호 : {broker_org_no}, 주문번호 : {broker_order_no}, "
                f"체결구분 : {ccld_div}, 거래소 구분 : {exchange_type}"
            )
            return daily_execution_response
        except KISOrderError:
            logger.error("주식 일별 주문 체결 조회 실패 (브로커 에러)")
            raise
        except Exception as e:
            logger.error(f"주식 일별 주문 체결 조회 실패 (예상치 못한 오류): {e}")
            raise
    
    
    # ⚙️ 국내 주식 주문 취소 요청 - revise_cancel_type='02'로 고정, 전체취소/일부취소는 qty_all_order_yn + quantity 조합으로 처리
    async def cancel_domestic_stock(
        self,
        access_token: str,
        order_no: str,
        krx_fwdg_ord_orgno: str = "",
        quantity: str = "0",
        qty_all_order_yn: str = "Y",
        order_type: str = ORD_DVSN_KRX.MARKET.value,
    ) -> OrderResponse:
        """
        주문 취소
        - revise_cancel_type='02'
        - 전체취소면 qty_all_order_yn='Y'
        - 일부취소면 qty_all_order_yn='N' + quantity 지정
        """
        # 입력값 검증
        self._validate_cancel_inputs(
            order_no=order_no,
            quantity=quantity,
            qty_all_order_yn=qty_all_order_yn,
        )
        logger.info(
            f"주문 취소 서비스 호출 - 원주문번호: {order_no}, "
            f"KRX전송주문조직번호: {krx_fwdg_ord_orgno}, 수량: {quantity}, "
            f"전체취소여부: {qty_all_order_yn}"
        )
        
        try:
            response = await self.kis_order.modify_order_by_cash(
                access_token=access_token,
                account_no=settings.KIS_ACCOUNT_NO,
                account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
                krx_fwdg_ord_orgno=krx_fwdg_ord_orgno,
                order_no=order_no,
                order_type=order_type,
                revise_cancel_type="02",    # 취소
                quantity=quantity,
                revise_price="0",           # 주문 취소는 정정가 없으므로 "0" 고정
                qty_all_order_yn=qty_all_order_yn,
                exchange_type=EXCG_ID_DVSN_CD.KRX.value,
            )
            logger.info(
                f"주문 취소 성공 - 원주문번호: {order_no}, "
                f"신규주문번호: {response.output.ODNO if response.output else ''}"
            )
            return response
        except KISOrderError:
            logger.error(f"주문 취소 실패 - 원주문번호: {order_no}")
            raise
        except Exception as e:
            logger.error(f"주문 취소 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ 국내 주식 주문 정정 요청 - 시장가/지정가 정규화는 기존 주문과 동일하게 처리, revise_cancel_type='01'로 고정
    async def revise_domestic_stock(
        self,
        access_token: str,
        order_no: str,
        quantity: str,
        order_type: ORD_DVSN_KRX.MARKET.value,
        price: str,
        krx_fwdg_ord_orgno: str = "",
        qty_all_order_yn: str = "N",
    ) -> OrderResponse:
        """
        주문 정정
        - revise_cancel_type='01'
        - 시장가/지정가 정규화는 기존 주문과 동일하게 처리
        - 전체정정이면 qty_all_order_yn='Y', 일부정정이면 qty_all_order_yn='N' + quantity 지정
        """
        # 입력값 검증
        self._validate_cancel_inputs(
            order_no=order_no,
            quantity=quantity,
            qty_all_order_yn=qty_all_order_yn,
        )
        
        order_mode, normalized_price = self._resolve_order_params(order_type, price)
        
        logger.info(
            f"주문 정정 서비스 호출 - 원주문번호: {order_no}, "
            f"KRX전송주문조직번호: {krx_fwdg_ord_orgno}, 수량: {quantity}, "
            f"주문유형: {order_mode}, 정정가격: {normalized_price}"
        )
        try:
            response = await self.kis_order.modify_order_by_cash(
                access_token=access_token,
                account_no=settings.KIS_ACCOUNT_NO,
                account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
                krx_fwdg_ord_orgno=krx_fwdg_ord_orgno,
                order_no=order_no,
                order_type=order_mode,
                revise_cancel_type="01",    # 정정
                quantity=quantity,
                revise_price=normalized_price,
                qty_all_order_yn=qty_all_order_yn,
                exchange_type=EXCG_ID_DVSN_CD.KRX.value,
            )
            logger.info(
                f"주문 정정 성공 - 원주문번호: {order_no}, "
                f"신규주문번호: {response.output.ODNO if response.output else ''}"
            )
            return response
        except KISOrderError:
            logger.error(f"주문 정정 실패 - 원주문번호: {order_no}")
            raise
        except Exception as e:
            logger.error(f"주문 정정 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ 정정/취소 가능 주문 목록 조회 (주문 번호, 주문 유형, 매도/매수 구분 등 주요 정보 포함)
    # NOTE: KIS 모의투자는 이 API를 지원하지 않으므로, 실계좌에서만 호출 가능하도록 구현
    async def list_cancelable_orders(
        self,
        access_token: str,
        inquire_div1: str = "0",
        inquire_div2: str = "0",
        account_no: str | None = None,
        account_product_code: str | None = None,
    ) -> ModifiableOrdersResponse:
        """
        정정/취소 가능 주문 목록 조회
        주의: KIS 모의투자는 미지원
        """
        if settings.TRADING_ENV == "paper":
            raise ValueError("정정/취소 가능 주문 목록 조회 API는 모의투자 환경에서 지원되지 않습니다.")
        
        logger.info(
            f"정정/취소 가능 주문 목록 조회 서비스 호출 - "
            f"inquire_div1: {inquire_div1}, inquire_div2: {inquire_div2}"
        )
        try:
            response = await self.kis_order.get_cancelable_cash_orders(
                access_token=access_token,
                account_no=settings.KIS_ACCOUNT_NO,
                account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
                inquire_div1=inquire_div1,
                inquire_div2=inquire_div2,
            )
            logger.info("정정/취소 가능 주문 목록 조회 성공")
            return response
        except KISOrderError:
            logger.error("정정/취소 가능 주문 목록 조회 실패")
            raise
        except Exception as e:
            logger.error(f"정정/취소 가능 주문 목록 조회 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ 일별 주문 체결 조회 - 다양한 필터링 옵션 지원 (매도/매수 구분, 종목 코드, 주문 번호 등)
    async def list_daily_order_executions(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        sell_buy_div: str = SLL_BUY_DVSN_CD.ALL.value,
        stock_code: str = "",
        broker_org_no: str = "",
        broker_order_no: str = "",
        ccld_div: str = CCDL_DVSN_CD.ALL.value,
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
        account_no: str | None = None,
        account_product_code: str | None = None,
    ) -> DailyOrderExecutionResponse:
        resolved_account_no = self._default_account_no(account_no)
        resolved_account_product_code = self._default_account_product_code(account_product_code)

        try:
            response = await self.kis_order.get_daily_order_executions(
                access_token=access_token,
                account_no=resolved_account_no,
                account_product_code=resolved_account_product_code,
                start_date=start_date,
                end_date=end_date,
                sell_buy_div=sell_buy_div,
                stock_code=stock_code,
                broker_org_no=broker_org_no,
                broker_order_no=broker_order_no,
                ccld_div=ccld_div,
                exchange_type=exchange_type,
            )

            logger.info(
                f"주식 일별 주문 체결 조회 성공 - "
                f"조회기간: {start_date} ~ {end_date}, "
                f"매수/매도구분: {sell_buy_div}, 종목코드: {stock_code}, "
                f"주문채번지점번호: {broker_org_no}, 주문번호: {broker_order_no}, "
                f"체결구분: {ccld_div}, 거래소구분: {exchange_type}"
            )
            return response

        except KISOrderError:
            logger.error("주식 일별 주문 체결 조회 실패")
            raise
        except Exception as e:
            logger.error(f"주식 일별 주문 체결 조회 실패 - 예상치 못한 오류: {e}")
            raise
    
    
    # ⚙️ worker-2 에서 사용하는 일별 주문 체결 조회 래퍼(워커 호환용)
    async def get_order_execution_result(
        self,
        access_token: str,
        start_date: str,
        end_date: str,
        sell_buy_div: str = "all",
        stock_code: str = "",
        broker_org_no: str = "",
        broker_order_no: str = "",
        ccld_div: str = "all",
        exchange_type: str = EXCG_ID_DVSN_CD.KRX.value,
        account_no: str | None = None,
        account_product_code: str | None = None,
    ) -> DailyOrderExecutionResponse:
        """
        주문 상태 추적 워커에서 사용하는 일별 주문 체결 조회 래퍼.
        기존 워커 호출 시그니처를 유지하면서도, 테스트에서는 이 메서드 또는
        하위 KISOrder.get_daily_order_executions 만 선택적으로 monkeypatch 할 수 있다.
        """
        return await self.get_daily_order_executions(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            sell_buy_div=sell_buy_div,
            stock_code=stock_code,
            broker_org_no=broker_org_no,
            broker_order_no=broker_order_no,
            ccld_div=ccld_div,
            exchange_type=exchange_type,
            account_no=account_no,
            account_product_code=account_product_code,
        )