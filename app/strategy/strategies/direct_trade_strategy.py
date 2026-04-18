"""
DIRECT_TRADE 유형 전략의 공통 인터페이스.

단일 종목 단위로 진입/청산을 결정하는 전략의 추상 클래스.
Executor는 이 인터페이스에 의존해 DIRECT_TRADE 전략을 실행한다.

⭐ REBALANCE와의 차이
    - REBALANCE: 리밸런싱 주기에 포트폴리오 diff 계산 → 전체 매도/매수
    - DIRECT_TRADE: 종목별로 진입/청산을 독립 판정 → 개별 매매
"""
from abc import abstractmethod

import pandas as pd

from app.strategy.strategies.base_strategy import BaseStrategy
from app.schemas.strategy.simulation import SwingPosition, SwingTradeRecord
from app.schemas.strategy.trading import ExitDecision


class DirectTradeStrategy(BaseStrategy):
    """
    단일 종목 매매 전략의 공통 계약.
    
    ⭐ 책임 분리
        - 전략(본 클래스): 진입/청산 판정, 포지션 사이징 로직을 소유
        - Executor: 시간 루프 관리, 포지션 장부 관리, 일별 평가만 담당
    
    ⭐ 구현해야 할 메서드
        - should_exit()            : 포지션별 청산 여부 판정
        - generate_entry_signals() : 진입 시그널 생성 (필터 포함)
        - size_position()          : 포지션 사이즈 결정
    
    ⭐ 기존 BaseStrategy에서 상속받는 것
        - strategy_type (property)
        - execute() (실전 파이프라인)
    """
    
    # ⚙️ 포지션 청산 판정
    @abstractmethod
    def should_exit(
        self,
        position: SwingPosition,
        date: pd.Timestamp,
        data: dict[str, pd.DataFrame],
    ) -> ExitDecision:
        """
        주어진 포지션을 현재 날짜(date) 기준으로 청산할지 판정.
        
        Args:
            position: 현재 보유 중인 포지션
            date: 판정 기준 날짜 (오늘)
            data: 전체 OHLCV 딕셔너리 (종목 코드 → 일별 DataFrame)
        
        Returns:
            ExitDecision: should_exit=True면 Executor가 매도 집행
        """
        ...
    
    
    # ⚙️ 진입 시그널 생성
    @abstractmethod
    def generate_entry_signals(
        self,
        date: pd.Timestamp,
        df_universe: pd.DataFrame,
        preloaded_data: dict[str, pd.DataFrame],
        current_positions: list[SwingPosition],
        recent_trade_history: list[SwingTradeRecord],
    ) -> pd.DataFrame:
        """
        현재 시점의 진입 시그널을 산출.
        
        순수 시그널 계산(scan_from_data)뿐 아니라 전략 고유의 진입 필터
        (쿨다운, 기보유 제외, 하락장 필터 등)까지 포함한 "최종 후보"를 반환한다.
        
        Args:
            date: 판정 기준 날짜
            df_universe: 유니버스 DataFrame (Code, Name, Marcap, AvgAmount 등)
            preloaded_data: 종목별 OHLCV 딕셔너리
            current_positions: 현재 보유 포지션 리스트 (기보유 제외에 사용)
            recent_trade_history: 최근 청산 이력 (쿨다운 판정에 사용)
                                  Executor가 충분히 긴 윈도우로 잘라서 전달
        
        Returns:
            pd.DataFrame: 최종 진입 후보. 최소 ["Code", "Name"] 컬럼을 포함하고,
                          전략별 부가 정보(return_pct, volume_ratio 등) 포함 가능.
        """
        ...
    
    
    # ⚙️ 포지션 사이징
    @abstractmethod
    def size_position(
        self,
        signal: pd.Series,
        available_cash: float,
        total_equity: float,
        num_new_entries: int,
    ) -> float:
        """
        단일 진입 시그널에 대해 투입할 주문 금액을 결정.
        
        Executor는 반환된 금액을 당일 종가로 나눠 수량을 산출한다.
        (실전 전환 시 주가 호가 단위 반올림 로직은 Executor에서 처리)
        
        Args:
            signal: 진입 후보 1건 (generate_entry_signals 반환값의 한 행)
            available_cash: 현재 가용 현금
            total_equity: 포트폴리오 전체 평가액 (현금 + 보유가치)
            num_new_entries: 이번 턴에 들어갈 신규 진입 종목 수
        
        Returns:
            float: 이 시그널에 배분할 주문 금액 (원)
        """
        ...