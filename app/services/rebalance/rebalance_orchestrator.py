"""리밸런싱 실행 오케스트레이터.

라우터(수동)와 Celery 태스크(자동) 양쪽에서 공용으로 사용하는 진입점.
전략 실행 + Executor 라우팅 + 결과 통합을 담당한다.

라우터는 HTTP 응답 변환만, Celery는 윈도우 체크만 추가로 담당하면 됨.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.strategy.trading import RebalanceResult, StrategyResult
from app.strategy.runtime.executor_registry import get_executor
from app.strategy.strategies.base_strategy import BaseStrategy

KST = ZoneInfo("Asia/Seoul")


@dataclass
class RebalanceOrchestratorResult:
    """리밸런싱 오케스트레이터 실행 결과.
    
    라우터는 strategy_result에서 이름/타입을, rebalance_result에서 매매 결과를
    추출해 HTTP 응답으로 변환한다.
    """
    strategy_result: StrategyResult
    rebalance_result: RebalanceResult


class RebalanceOrchestrator:
    """리밸런싱 전략 실행 + 주문 실행 조립.
    
    수동(라우터)/자동(Celery) 공용 진입점. 비즈니스 로직 자체는
    Strategy + Executor가 담당하고, 본 클래스는 둘을 조립해 호출만 한다.
    
    Args:
        strategy: 실행할 전략 인스턴스 (DI로 주입)
    """
    
    def __init__(self, strategy: BaseStrategy):
        self._strategy = strategy
    
    async def run(
        self,
        db: AsyncSession,
        year: int | None = None,
        dry_run: bool = True,
    ) -> RebalanceOrchestratorResult:
        """전략 실행 → Executor 라우팅 → 매매 실행.
        
        Args:
            db: DB 세션
            year: 백테스트/스크리닝 기준 연도. None이면 현재 연도 (KST 기준).
            dry_run: True면 실제 주문 안 함.
        
        Returns:
            전략 결과 + 매매 결과를 담은 컨테이너
        """
        # 1. year 추론
        if year is None:
            # year = datetime.now(KST).year
            year = self._infer_latest_available_fiscal_year()
        
        # 2. 전략 실행 (종목 선정)
        strategy_result = await self._strategy.execute(year=year)
        
        # 3. Executor 라우팅 + 매매 실행
        executor = get_executor(self._strategy.strategy_type)
        rebalance_result = await executor.submit(
            result=strategy_result,
            db=db,
            dry_run=dry_run,
        )
        
        return RebalanceOrchestratorResult(
            strategy_result=strategy_result,
            rebalance_result=rebalance_result,
        )
    
    
    @staticmethod
    def _infer_latest_available_fiscal_year(now: datetime | None = None) -> int:
        """현재 시점에 사용 가능한 최신 사업보고서 연도 추론.
        
        한국 상장사 사업보고서는 사업연도 종료 후 90일 이내(3/31) 공시 의무.
        실무상 4월 초까지 공시 지연/정정 가능성을 고려해 4월 중순 이후를 안전 기준으로 잡음.
        
        예시:
            2026-04-29 → 2025 (2025년 사업보고서)
            2026-03-15 → 2024 (2025년 보고서 미공시)
            2027-01-15 → 2025 (2026년 보고서 아직 미공시)
        """
        now = now or datetime.now(KST)
        
        # 4월 15일 이후면 직전년도 사업보고서 사용 가능
        fiscal_cutoff = date(now.year, 4, 15)
        if now.date() >= fiscal_cutoff:
            return now.year - 1
        else:
            return now.year - 2