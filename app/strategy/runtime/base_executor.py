from abc import ABC, abstractmethod
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.strategy.trading import StrategyResult


class BaseExecutor(ABC):
    """
    전략 실행기 베이스 클래스
    
    Strategy.execute()가 반환한 StrategyResult를 받아
    실제 주문 실행을 처리한다.
    
    - RebalanceExecutor: 계좌 조회 → diff 계산 → 매도/매수 주문
    - DirectTradeExecutor: TradeIntent를 바로 주문 (향후)
    """

    @abstractmethod
    async def submit(
        self,
        result: StrategyResult,
        db: AsyncSession,
        dry_run: bool = True,
    ) -> dict:
        """
        전략 결과를 받아 주문 실행

        Parameters
        ----------
        result : Strategy.execute() 반환값
        db : SQLAlchemy async session
        dry_run : True면 주문 생성 없이 계획만 반환

        Returns
        -------
        dict : 실행 결과 (Executor 유형별로 다를 수 있음)
        """
        ...