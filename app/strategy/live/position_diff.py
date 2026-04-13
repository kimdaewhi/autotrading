"""
⭐ Position Diff Calculator
    리밸런싱 시점에 [현재 보유 포트폴리오]와 [목표 포트폴리오]의 차이를 계산하여
    매도/매수 주문 리스트를 생성하는 모듈

    흐름:
        1. 목표 포트폴리오: MomentumStrategy.generate_signal() → BUY 종목 리스트
        2. 현재 포트폴리오: AccountService.get_holding_list() → 보유 종목/수량
        3. diff 계산:
            - 청산 대상: 보유 중인데 목표에 없는 종목
            - 신규 매수 대상: 목표에 있는데 미보유 종목
            - 유지 대상: 양쪽 모두 존재하는 종목 (비중 조정 가능)
        4. 주문 수량 계산:
            - 균등 비중: 총 투자금 / BUY 종목 수 = 종목당 투자금
            - 종목당 투자금 / 현재가 → 정수 주(floor)
"""

import math
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import get_logger
from app.schemas.strategy.rebalance import CurrentHolding, PositionDiffItem, PositionDiffResult

logger = get_logger(__name__)


class DiffAction(str, Enum):
    """포지션 변경 액션"""
    SELL = "SELL"       # 전량 청산
    BUY = "BUY"         # 신규 매수
    HOLD = "HOLD"       # 유지 (변동 없음)
    REBALANCE = "REBALANCE"  # 비중 조정 (향후 확장용)


@dataclass
class PositionDiffItem:
    """개별 종목의 포지션 변경 정보"""
    stock_code: str
    stock_name: str
    action: DiffAction
    
    # 현재 보유 정보
    current_qty: int = 0
    current_price: int = 0          # 현재가 (원)
    current_value: int = 0          # 평가금액 (원)
    
    # 목표 정보
    target_qty: int = 0
    target_value: int = 0           # 목표 투자금 (원)
    
    # 주문 정보 (계산 결과)
    order_qty: int = 0              # 실제 주문 수량
    order_value: int = 0            # 예상 주문 금액 (원)
    
    # 모멘텀 부가 정보
    momentum_return: float = 0.0
    momentum_rank: int = 0


class PositionDiffCalculator:
    """
    ⭐ 포지션 Diff 계산기
    
    현재 보유 포트폴리오와 전략 시그널(목표 포트폴리오)을 비교하여
    매도/매수 주문 리스트를 생성한다.
    
    Parameters
    ----------
    allocation_method : str
        비중 배분 방식. 현재는 "equal"(균등 비중)만 지원.
    order_price_type : str
        주문 가격 타입. "market"(시장가) 또는 "limit"(지정가).
    cash_buffer_ratio : float
        매수 시 현금 버퍼 비율. 슬리피지/수수료 대비 여유분.
        ex) 0.02 → 총 매수 가능 금액의 2%를 현금으로 남김.
    """
    
    def __init__(
        self,
        allocation_method: str = "equal",
        order_price_type: str = "market",
        cash_buffer_ratio: float = 0.02,
    ):
        self.allocation_method = allocation_method
        self.order_price_type = order_price_type
        self.cash_buffer_ratio = cash_buffer_ratio
    
    
    def calculate(
        self,
        buy_codes: list[str],                   # 전략에서 BUY 시그널이 발생한 종목 코드 리스트
        signal_df,                              # 전략의 generate_signal() 반환값 (index=종목코드, columns=[signal, return, rank])
        current_holdings: list[CurrentHolding], # 현재 계좌의 보유 종목 리스트
        available_cash: int,                    # 현재 예수금 (원)
        price_map: dict[str, int],              # {종목코드: 매매가} 매핑 (BUY 종목의 매매 가격 조회 결과)
        name_map: dict[str, str] | None = None, # {종목코드: 종목명} 매핑 (없으면 코드로 표시)
    ) -> PositionDiffResult:
        """
        포지션 diff 계산 메인 로직
        
        Parameters
        ----------
        buy_codes : 전략의 BUY 시그널 종목 코드 리스트
        signal_df : 전략의 generate_signal() 반환값 (index=종목코드, columns=[signal, return, rank])
        current_holdings : 현재 보유 종목 리스트 (AccountService에서 조회)
        available_cash : 현재 예수금 (원)
        price_map : {종목코드: 매매 기준가} 매핑 (BUY 종목의 매매 가격 조회 결과)
        name_map : {종목코드: 종목명} 매핑 (없으면 코드로 표시)
        """
        name_map = name_map or {}
        buy_set = set(buy_codes)
        holding_map = {h.stock_code: h for h in current_holdings}
        
        # 초기화(예수금, 매매해야 할 종목 개수, 현재 계좌의 보유 종목 개수)
        result = PositionDiffResult(
            available_cash=available_cash,
            target_count=len(buy_codes),
            current_count=len(current_holdings),
        )
        
        # ── 1. 분류: 매도 / 유지 / 신규매수 ──
        
        # 1-1. 현재 보유 종목 순회 → 매도 또는 유지 결정
        for code, holding in holding_map.items():
            if code in buy_set:
                # 목표에도 있으니 유지
                item = PositionDiffItem(
                    stock_code=code,
                    stock_name=holding.stock_name,
                    action=DiffAction.HOLD,
                    current_qty=holding.quantity,
                    current_price=holding.current_price,
                    current_value=holding.eval_amount,
                )
                result.hold_list.append(item)
            else:
                # 목표에 없으니 전량 매도
                item = PositionDiffItem(
                    stock_code=code,
                    stock_name=holding.stock_name,
                    action=DiffAction.SELL,
                    current_qty=holding.quantity,
                    current_price=holding.current_price,
                    current_value=holding.eval_amount,
                    order_qty=holding.quantity,
                    order_value=holding.quantity * holding.current_price,
                )
                result.sell_list.append(item)
                result.total_sell_value += item.order_value
        
        # 1-2. BUY 시그널 중 미보유 종목 → 신규 매수 대상
        new_buy_codes = [code for code in buy_codes if code not in holding_map]
        
        # ── 2. 매수 수량 계산 (균등 비중) ──
        
        # 매수 가능 총액 = 예수금 + 매도 예상 금액 - 버퍼
        total_investable = available_cash + result.total_sell_value     # 총 투자금 = 예수금 + 매도 예상 금액
        cash_buffer = int(total_investable * self.cash_buffer_ratio)    # 현금 버퍼 (슬리피지/수수료 대비 여유분)
        net_investable = total_investable - cash_buffer                 # 버퍼를 제외한 실제 매수 가능 금액(최종 투자금)
        
        # 유지 종목의 현재 평가액도 고려하여 신규 매수 종목에 배분
        # 균등 비중: 전체 포트폴리오 가치를 목표 종목 수로 나눔
        hold_value = sum(item.current_value for item in result.hold_list)   # 유지 종목의 총 평가액
        total_portfolio_value = net_investable + hold_value                 # 전체 포트폴리오 가치 = 매수 가능 금액 + 유지 종목 평가액
        
        if len(buy_codes) > 0:
            # 목표 종목 수로 전체 포트폴리오 가치를 나누어 종목당 목표 투자금 계산
            target_value_per_stock = total_portfolio_value / len(buy_codes)
        else:
            target_value_per_stock = 0
        
        # 신규 매수 종목에 실제 배분할 금액
        # = (신규 매수 종목 수 × 종목당 목표) 와 net_investable 중 작은 값
        total_new_buy_target = target_value_per_stock * len(new_buy_codes)
        actual_buy_budget = min(total_new_buy_target, net_investable)
        
        if new_buy_codes and actual_buy_budget > 0:
            alloc_per_stock = actual_buy_budget / len(new_buy_codes)
            
            for code in new_buy_codes:
                price = price_map.get(code, 0)
                if price <= 0:
                    logger.warning(f"[{code}] 현재가 조회 실패 - 매수 대상에서 제외")
                    continue
                
                # 정수 주 계산 (floor)
                qty = math.floor(alloc_per_stock / price)
                if qty <= 0:
                    logger.warning(
                        f"[{code}] 매수 수량 0주 (종목당 배분: {alloc_per_stock:,.0f}원, "
                        f"현재가: {price:,}원) - 매수 대상에서 제외"
                    )
                    continue
                
                order_value = qty * price
                
                # 모멘텀 부가 정보
                momentum_return = 0.0
                momentum_rank = 0
                if signal_df is not None and code in signal_df.index:
                    momentum_return = float(signal_df.loc[code, "return"])
                    momentum_rank = int(signal_df.loc[code, "rank"])
                
                item = PositionDiffItem(
                    stock_code=code,
                    stock_name=name_map.get(code, code),
                    action=DiffAction.BUY,
                    current_price=price,
                    target_qty=qty,
                    target_value=int(alloc_per_stock),
                    order_qty=qty,
                    order_value=order_value,
                    momentum_return=momentum_return,
                    momentum_rank=momentum_rank,
                )
                result.buy_list.append(item)
                result.total_buy_value += order_value
        
        # ── 3. 잔여 현금 계산 ──
        result.estimated_cash_after = (
            available_cash
            + result.total_sell_value
            - result.total_buy_value
        )
        
        # ── 4. 로깅 ──
        logger.info(
            f"포지션 diff 계산 완료: "
            f"매도 {len(result.sell_list)}종목({result.total_sell_value:,.0f}원), "
            f"매수 {len(result.buy_list)}종목({result.total_buy_value:,.0f}원), "
            f"유지 {len(result.hold_list)}종목, "
            f"잔여현금 {result.estimated_cash_after:,.0f}원"
        )
        
        return result