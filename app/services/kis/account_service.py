import redis.asyncio as redis
from app.broker.kis.kis_account import KISAccount
from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
import app.schemas.kis.account as account_schemas
from app.schemas.kis.kis import BalanceResponse
from app.services.kis.auth_service import AuthService



class AccountService:
    """ 
    _summary_
    계좌 서비스 클래스
    
    _description_
    계좌 관련 기능을 제공하는 서비스 클래스입니다.
    """
    def __init__(self, kis_account: KISAccount) -> None:
        self.kis_account = kis_account
    
    
    # ⚙️ 문자열 숫자 → 정수/실수 변환 헬퍼 메서드
    @staticmethod
    def _to_int(value: str | None) -> int:
        if not value:
            return 0
        return int(float(value))
    
    
    # ⚙️ 문자열 숫자 → 실수 변환 헬퍼 메서드
    @staticmethod
    def _to_float(value: str | None) -> float:
        if not value:
            return 0.0
        return float(value)
    
    
    # ⚙️ 계좌 잔고 조회
    async def get_account_balance(self) -> BalanceResponse:
        # 1. Redis 클라이언트 생성 및 access token 발급(or 사용)
        redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
        auth_service = AuthService(
            auth_broker=KISAuth(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=f"{settings.kis_base_url}",
            ),
            redis_client=redis_client,
        )
        access_token = await auth_service.get_valid_access_token()
        
        # 2. KISAccount broker 통해 계좌 잔고 조회
        balance = await self.kis_account.get_balance(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        )
        return balance
    
    
    # ⚙️ 보유종목 목록 조회
    async def get_holding_list(self) -> list[account_schemas.HoldingRead]:
        balance = await self.get_account_balance()
        
        summary = balance.output2[0] if balance.output2 else None
        
        # ✔️ 보유종목 평가금액 합계 (종목 기준 비중용)
        total_stock_evaluation_amount = (
            self._to_int(summary.evlu_amt_smtl_amt) if summary else 0
        )
        
        holdings: list[account_schemas.HoldingRead] = []
        
        for item in balance.output1:
            evaluation_amount = self._to_int(item.evlu_amt)
            
            weight_rate = "0"
            if total_stock_evaluation_amount > 0:
                weight_rate = str(
                    round((evaluation_amount / total_stock_evaluation_amount) * 100, 2)
                )
            
            holdings.append(
                account_schemas.HoldingRead(
                    stock_code=item.pdno,
                    stock_name=item.prdt_name,
                    holding_qty=item.hldg_qty,
                    orderable_qty=item.ord_psbl_qty,
                    avg_buy_price=item.pchs_avg_pric,
                    current_price=item.prpr,
                    purchase_amount=item.pchs_amt,
                    evaluation_amount=item.evlu_amt,
                    profit_loss_amount=item.evlu_pfls_amt,
                    profit_loss_rate=item.evlu_pfls_rt,
                    weight_rate=weight_rate,
                )
            )
        
        return holdings
    
    
    # ⚙️ 계좌 요약 정보 가공
    async def get_account_summary(self) -> account_schemas.AccountSummaryRead:
        # 1. raw data 조회 및 계좌 요약 정보 가공
        balance = await self.get_account_balance()
        summary = balance.output2[0]
        
        # TODO(P2/지표) : 계좌 수익률 별도 정의 필요 (ROADMAP #7). 순투입자금 기준 / TWR 등 정책 결정 후 구현
        # 현재 asset_change_rate는 한투에서 제공하는 전일 대비 자산증감률을 그대로 사용 중.
        #
        # 별도의 "계좌 수익률" 지표를 정의할 필요가 있음.
        #
        # 수익률 정의는 단순 계산 문제가 아니라 도메인 정책에 따라 달라짐:
        # - 순투입자금 기준 수익률 (입출금 반영)
        # - 총 매입금액 대비 수익률 (포지션 기준)
        # - 시간가중 수익률(TWR) 등
        #
        # 특히 입출금/추가입금이 발생하는 경우 수익률 계산 방식이 크게 달라지므로,
        # 명확한 기준 정의 후 별도 필드로 분리하여 제공하는 것이 적절함.
        #
        # → 현재는 전일 대비 지표 유지, 향후 "계좌 수익률" 별도 정의 및 추가 예정

        return account_schemas.AccountSummaryRead(
            cash_amount=summary.dnca_tot_amt,                   # 주문 가능 현금(예수금)
            settlement_cash_amount=summary.prvs_rcdl_excc_amt,  # 정산 기준 현금(D+2)
            stock_evaluation_amount=summary.scts_evlu_amt,
            total_evaluation_amount=summary.tot_evlu_amt,
            net_asset_amount=summary.nass_amt,
            total_purchase_amount=summary.pchs_amt_smtl_amt,
            total_profit_loss_amount=summary.evlu_pfls_smtl_amt,
            asset_change_amount=summary.asst_icdc_amt,
            asset_change_rate=summary.asst_icdc_erng_rt,
        )
    
    
    # ⚙️ 수익/손실 종목 분리
    async def get_profit_loss_holdings(self) -> tuple[list[account_schemas.HoldingRead], list[account_schemas.HoldingRead]]:
        # 보유 종목 목록을 기준으로 수익/손실 종목 분리
        holdings = await self.get_holding_list()
        
        profit_holdings: list[account_schemas.HoldingRead] = []
        loss_holdings: list[account_schemas.HoldingRead] = []
        
        for holding in holdings:
            profit_loss_amount = self._to_float(holding.profit_loss_amount)
            
            # 평가손익 기준으로 수익/손실 분리
            if profit_loss_amount > 0:
                profit_holdings.append(holding)
            elif profit_loss_amount < 0:
                loss_holdings.append(holding)
        
        return profit_holdings, loss_holdings
    
    
    # ⚙️ 주문가능수량 기준 매도 가능 종목 목록 조회
    async def get_sellable_holdings(self) -> list[account_schemas.HoldingRead]:
        # 보유 종목 중 주문가능수량이 1주 이상인 종목만 추출
        holdings = await self.get_holding_list()
        
        sellable_holdings = [
            holding
            for holding in holdings
            if self._to_int(holding.orderable_qty) > 0
        ]
        
        return sellable_holdings
    
    
    # ⚙️ 당일 매매 현황 조회
    async def get_today_trading_summary(self) -> account_schemas.TodayTradingSummaryRead:
        balance = await self.get_account_balance()

        output1 = balance.output1 or []
        output2 = balance.output2 or []
        summary = output2[0] if output2 else None

        # output2 우선: 금일(thdt) -> 전일(bfdy) fallback
        today_buy_amount = 0
        today_sell_amount = 0

        if summary:
            thdt_buy_amt = self._to_int(getattr(summary, "thdt_buy_amt", "0"))
            thdt_sll_amt = self._to_int(getattr(summary, "thdt_sll_amt", "0"))
            bfdy_buy_amt = self._to_int(getattr(summary, "bfdy_buy_amt", "0"))
            bfdy_sll_amt = self._to_int(getattr(summary, "bfdy_sll_amt", "0"))

            today_buy_amount = thdt_buy_amt if thdt_buy_amt > 0 else bfdy_buy_amt
            today_sell_amount = thdt_sll_amt if thdt_sll_amt > 0 else bfdy_sll_amt

        # 수량도 동일하게 금일(thdt) -> 전일(bfdy) fallback
        today_buy_qty = 0
        today_sell_qty = 0

        fallback_buy_amount = 0
        fallback_sell_amount = 0

        for item in output1:
            thdt_buy_qty = self._to_int(getattr(item, "thdt_buyqty", "0"))
            thdt_sll_qty = self._to_int(getattr(item, "thdt_sll_qty", "0"))
            bfdy_buy_qty = self._to_int(getattr(item, "bfdy_buy_qty", "0"))
            bfdy_sll_qty = self._to_int(getattr(item, "bfdy_sll_qty", "0"))

            buy_qty = thdt_buy_qty if thdt_buy_qty > 0 else bfdy_buy_qty
            sell_qty = thdt_sll_qty if thdt_sll_qty > 0 else bfdy_sll_qty

            current_price = self._to_int(getattr(item, "prpr", "0"))

            today_buy_qty += buy_qty
            today_sell_qty += sell_qty

            fallback_buy_amount += buy_qty * current_price
            fallback_sell_amount += sell_qty * current_price

        # output2 금액도 둘 다 0이면 output1 기반 추정치 사용
        if today_buy_amount <= 0:
            today_buy_amount = fallback_buy_amount

        if today_sell_amount <= 0:
            today_sell_amount = fallback_sell_amount

        return account_schemas.TodayTradingSummaryRead(
            today_buy_amount=str(today_buy_amount),
            today_sell_amount=str(today_sell_amount),
            today_buy_qty=str(today_buy_qty),
            today_sell_qty=str(today_sell_qty),
        )
    
    
    # ⚙️ 보유 종목 수 / 총 보유 수량 조회
    async def get_holding_stats(self) -> account_schemas.HoldingStatsRead:
        # 보유 종목 목록 기준으로 종목 수와 총 보유 수량 계산
        holdings = await self.get_holding_list()
        
        holding_stock_count = len(holdings)
        total_holding_qty = sum(self._to_int(holding.holding_qty) for holding in holdings)
        
        return account_schemas.HoldingStatsRead(
            holding_stock_count=str(holding_stock_count),
            total_holding_qty=str(total_holding_qty),
        )
    
    
    # ⚙️ 최고 수익 / 최고 손실 종목 조회
    async def get_top_profit_loss_holdings(self) -> account_schemas.TopHoldingPairRead:
        # 보유 종목 목록을 평가손익 기준으로 비교
        holdings = await self.get_holding_list()
        
        if not holdings:
            return account_schemas.TopHoldingPairRead(
                top_profit_holding=None,
                top_loss_holding=None,
            )
            
        # 평가손익이 가장 큰 종목 / 가장 작은 종목 추출
        top_profit_holding = max(
            holdings,
            key=lambda x: self._to_float(x.profit_loss_amount),
        )
        top_loss_holding = min(
            holdings,
            key=lambda x: self._to_float(x.profit_loss_amount),
        )
        
        return account_schemas.TopHoldingPairRead(
            top_profit_holding=top_profit_holding,
            top_loss_holding=top_loss_holding,
        )


