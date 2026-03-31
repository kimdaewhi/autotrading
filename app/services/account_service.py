import redis.asyncio as redis
from app.broker.kis.kis_account import KISAccount
from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
import app.schemas.account as account_schemas
from app.schemas.kis import BalanceResponse
from app.services.auth_service import AuthService



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
        # 1. raw data 조회 및 보유종목 데이터 가공
        balance = await self.get_account_balance()
        
        summary = balance.output2[0] if balance.output2 else None                       # 계좌 요약 정보 (보유종목별 평가금액 합계)
        total_evaluation_amount = self._to_int(summary.tot_evlu_amt) if summary else 0  # 총 평가금액
        
        # 3. 보유종목별 평가금액 기준 비중 계산 및 HoldingRead 모델로 변환
        holdings: list[account_schemas.HoldingRead] = []
        for item in balance.output1:
            evaluation_amount = self._to_int(item.evlu_amt)
            
            weight_rate = "0"
            if total_evaluation_amount > 0:
                weight_rate = str(round((evaluation_amount / total_evaluation_amount) * 100, 2))
                
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
        
        return account_schemas.AccountSummaryRead(
            cash_amount=summary.dnca_tot_amt,
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
        # raw 잔고 조회 응답의 output1/output2를 함께 사용
        balance = await self.get_account_balance()
        
        today_buy_qty = 0
        today_sell_qty = 0
        
        # 종목별 당일 매수/매도 수량 합산
        for item in balance.output1:
            today_buy_qty += self._to_int(item.thdt_buyqty)
            today_sell_qty += self._to_int(item.thdt_sll_qty)
            
        summary = balance.output2[0] if balance.output2 else None
        
        return account_schemas.TodayTradingSummaryRead(
            today_buy_amount=summary.thdt_buy_amt if summary else "0",
            today_sell_amount=summary.thdt_sll_amt if summary else "0",
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


