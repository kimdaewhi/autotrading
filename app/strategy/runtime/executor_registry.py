# runtime/executor_registry.py

from app.schemas.strategy.trading import StrategyType
from app.strategy.runtime.base_executor import BaseExecutor
from app.strategy.runtime.rebalance_executor import RebalanceExecutor
from app.services.kis.account_service import AccountService
from app.core.settings import settings
from app.broker.kis.kis_account import KISAccount


def get_executor(strategy_type: StrategyType) -> BaseExecutor:
    """strategy_type에 따라 적절한 Executor 반환"""
    if strategy_type == StrategyType.REBALANCE:
        return RebalanceExecutor(
            account_service=AccountService(
                kis_account=KISAccount(
                    appkey=settings.KIS_APP_KEY,
                    appsecret=settings.KIS_APP_SECRET,
                    url=settings.kis_base_url,
                )
            ),
        )
    elif strategy_type == StrategyType.DIRECT_TRADE:
        pass
    raise ValueError(f"지원하지 않는 전략 유형: {strategy_type}")