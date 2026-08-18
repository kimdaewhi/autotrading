import redis.asyncio as redis
from app.broker.kis.kis_account import KISAccount
from app.broker.kis.kis_auth import KISAuth
from app.core.settings import settings
import app.schemas.kis.account as account_schemas
from app.schemas.kis.kis import BalanceItem, BalanceResponse, BalanceSummary
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
    
    
    # ⚙️ 문자열 숫자 → 정수 변환 헬퍼 메서드
    @staticmethod
    def _to_int(value: str | None) -> int:
        if not value:
            return 0
        return int(float(value))
    
    
    # ⚙️ access token 발급(or 재사용)
    async def _get_access_token(self) -> str:
        redis_client = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)
        auth_service = AuthService(
            auth_broker=KISAuth(
                appkey=settings.KIS_APP_KEY,
                appsecret=settings.KIS_APP_SECRET,
                url=f"{settings.kis_base_url}",
            ),
            redis_client=redis_client,
        )
        return await auth_service.get_valid_access_token()
    
    
    # ⚙️ 보유 종목 조회 내부 메서드
    def _build_holding_list(self, holding_items: list[BalanceItem]) -> list[account_schemas.HoldingRead]:
        holdings: list[account_schemas.HoldingRead] = []
        
        for item in holding_items:
            holdings.append(
                account_schemas.HoldingRead(
                    stock_code=item.pdno,
                    stock_name=item.prdt_name,
                    holding_qty=item.hldg_qty,
                    avg_buy_price=item.pchs_avg_pric,
                    current_price=item.prpr,
                    purchase_amount=item.pchs_amt,
                    evaluation_amount=item.evlu_amt,
                    profit_loss_amount=item.evlu_pfls_amt,
                    profit_loss_rate=item.evlu_pfls_rt,
                )
            )
        
        return holdings
    
    
    # ⚙️ 계좌 요약 정보 조회 내부 메서드
    def _build_account_summary(self, summary: BalanceSummary, holding_stock_count: int) -> account_schemas.AccountSummaryRead:
        return account_schemas.AccountSummaryRead(
            settlement_cash_amount=summary.prvs_rcdl_excc_amt,  # 정산 기준 현금(D+2)
            stock_evaluation_amount=summary.scts_evlu_amt,      # 개별 종목 평가 금액
            total_evaluation_amount=summary.tot_evlu_amt,       # 정산 기준 현금 + 개별 종목 평가 금액
            net_asset_amount=summary.nass_amt,
            total_purchase_amount=summary.pchs_amt_smtl_amt,
            total_profit_loss_amount=summary.evlu_pfls_smtl_amt,
            holding_stock_count=str(holding_stock_count),
        )
    
    # ====================================================
    # 🛠️ 서비스 메서드 
    # ====================================================
    
    # ⚙️ 계좌 잔고 조회(실시간)
    async def get_account_balance(self) -> BalanceResponse:
        access_token = await self._get_access_token()
        
        balance = await self.kis_account.get_balance(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        )
        return balance
    
    
    # ⚙️ 보유종목 목록 조회
    async def get_holding_list(self) -> list[account_schemas.HoldingRead]:
        balance = await self.get_account_balance()
        holdings = self._build_holding_list(balance.output1 or [])
        
        return holdings
    
    
    # ⚙️ 계좌 요약 정보 가공
    async def get_account_summary(self) -> account_schemas.AccountSummaryRead:
        balance = await self.get_account_balance()
        holding_stock_count = 0
        
        # output2 가 비어 오는 경우 IndexError 대신 명시적 실패로 전환
        if not balance.output2:
            raise ValueError("계좌 잔고 응답에 요약 정보(output2)가 없습니다.")
        
        holding_stock_count = len(balance.output1 or [])
        
        return self._build_account_summary(balance.output2[0], holding_stock_count)
    
    
    # ⚙️ 매수 가능 금액 조회
    async def get_available_buy(self) -> int:
        access_token = await self._get_access_token()
        
        available_buy = await self.kis_account.get_available_buy(
            access_token=access_token,
            account_no=settings.KIS_ACCOUNT_NO,
            account_product_code=settings.KIS_ACCOUNT_PRODUCT_CODE,
        )
        
        # 모의 환경에서 두 값의 역전이 관측되어 방어적으로 최솟값 사용
        available_buy_amount = min(
            self._to_int(available_buy.output.ord_psbl_cash),
            self._to_int(available_buy.output.nrcvb_buy_amt),
        )
        
        return int(available_buy_amount)
    
    
    # ⚙️ 계좌 대시보드 조회 (요약 + 보유종목)
    async def get_dashboard(self) -> account_schemas.AccountDashboardRead:
        balance = await self.get_account_balance()   # 브로커 요청 1회
        
        if not balance.output2:
            raise ValueError("계좌 잔고 응답에 요약 정보(output2)가 없습니다.")
        
        return account_schemas.AccountDashboardRead(
            account_summary=self._build_account_summary(balance.output2[0], len(balance.output1 or [])),
            holding_list=self._build_holding_list(balance.output1 or []),
        )