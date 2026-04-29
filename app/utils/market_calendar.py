"""
KRX 영업일 판단 및 리밸런싱 실행 윈도우 정책 모듈.

QuantLib `SouthKorea.KRX` 캘린더를 베이스로 하고, QuantLib이 자동으로
반영하지 못하는 휴일(신규 입법 공휴일, 정부 임시공휴일 등)은
KRX_EXTRA_HOLIDAYS 상수에 수동 등록한다.

⚠️ 주의: QuantLib의 SouthKorea 캘린더는 클래스 레벨 휴일 저장소를 공유한다.
    여러 KrxCalendar 인스턴스를 만들어도 addHoliday()는 모든 인스턴스에 영향.
    운영상 KRX_EXTRA_HOLIDAYS는 한 가지 셋만 사용하므로 문제 없으나,
    테스트에서 서로 다른 extra_holidays를 주입할 경우 격리가 깨질 수 있음.

사용 예시:
    calendar = KrxCalendar()
    clock = SystemClock()
    window = RebalanceWindow(
        calendar=calendar,
        clock=clock,
        last_rebalance_date=date(2026, 4, 15),
    )
    decision = window.decide()
    if decision == WindowDecision.RUN_REBALANCE:
        # 종목 선정 + 주문 실행을 한 번에 수행
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum, auto
from typing import Protocol
from zoneinfo import ZoneInfo

import QuantLib as ql

from app.core.settings_rebalance import rebalance_settings

# ─────────────────────────────────────────────────────────────
# 수동 등록 영역: KRX 캘린더에 누락된 휴일을 추가한다.
# 운영 절차:
#   1) 정부가 임시공휴일 지정 시 (뉴스/관보 확인 후) 추가
#   2) 신규 입법으로 공휴일이 생기거나 변경 시 추가
#   3) KRX 연말 폐장일 변경 등 특수 케이스 추가
# ─────────────────────────────────────────────────────────────
KRX_EXTRA_HOLIDAYS: list[date] = [
    # 2026
    date(2026, 7, 17),   # 제헌절 (2026년부터 공휴일로 지정, QuantLib 미반영)
]

# 시간대 상수
KST = ZoneInfo("Asia/Seoul")

# ─────────────────────────────────────────────────────────────
# Clock: 시간 추상화 (테스트용)
# ─────────────────────────────────────────────────────────────
class Clock(Protocol):
    """현재 시각을 제공하는 인터페이스. 테스트 시 FixedClock으로 교체 가능."""
    
    def now(self) -> datetime:
        """tz-aware datetime (KST) 반환."""
        ...


class SystemClock:
    """운영용: 실제 시스템 시각 (KST)."""
    
    def now(self) -> datetime:
        return datetime.now(tz=KST)


@dataclass
class FixedClock:
    """테스트용: 주입된 고정 시각 반환."""
    
    fixed_now: datetime
    
    def now(self) -> datetime:
        # tz-aware 보장
        if self.fixed_now.tzinfo is None:
            return self.fixed_now.replace(tzinfo=KST)
        return self.fixed_now


# ─────────────────────────────────────────────────────────────
# KrxCalendar: QuantLib 래퍼 + 누락 휴일 보정
# ─────────────────────────────────────────────────────────────
class KrxCalendar:
    """KRX 영업일 판단을 위한 QuantLib 래퍼.
    
    내부적으로 `ql.SouthKorea(ql.SouthKorea.KRX)`를 사용하며,
    `KRX_EXTRA_HOLIDAYS`에 등록된 날짜를 추가 휴일로 등록한다.
    
    외부에는 표준 `datetime.date`만 노출하고, `ql.Date`는 모듈 내부에서만 사용.
    """
    
    def __init__(self, extra_holidays: list[date] | None = None):
        self._cal = ql.SouthKorea(ql.SouthKorea.KRX)
        # 누락 휴일 등록
        holidays = extra_holidays if extra_holidays is not None else KRX_EXTRA_HOLIDAYS
        for h in holidays:
            self._cal.addHoliday(self._to_ql(h))
    
    
    # 변환 헬퍼 (private)
    @staticmethod
    def _to_ql(d: date) -> ql.Date:
        return ql.Date(d.day, d.month, d.year)
    
    
    @staticmethod
    def _to_py(d: ql.Date) -> date:
        return date(d.year(), d.month(), d.dayOfMonth())
    
    
    # 공개 API
    def is_business_day(self, d: date) -> bool:
        """주어진 날짜가 KRX 영업일인지 반환"""
        return self._cal.isBusinessDay(self._to_ql(d))
    
    
    def next_business_day(self, d: date) -> date:
        """주어진 날짜 이후의 첫 영업일 반환 (d가 영업일이어도 그 다음 영업일)."""
        ql_d = self._to_ql(d)
        ql_next = self._cal.advance(ql_d, ql.Period(1, ql.Days))
        return self._to_py(ql_next)
    
    
    def previous_business_day(self, d: date) -> date:
        """주어진 날짜 이전의 직전 영업일 반환 (d가 영업일이어도 그 직전 영업일)."""
        ql_d = self._to_ql(d)
        ql_prev = self._cal.advance(ql_d, ql.Period(-1, ql.Days))
        return self._to_py(ql_prev)
    
    
    def adjust_to_next_business_day(self, d: date) -> date:
        """d가 영업일이면 그대로, 아니면 다음 영업일로 보정."""
        if self.is_business_day(d):
            return d
        return self.next_business_day(d)
    
    
    def add_business_days(self, d: date, n: int) -> date:
        """d로부터 n 영업일 후의 날짜 반환 (n이 음수면 이전 방향)."""
        ql_d = self._to_ql(d)
        ql_result = self._cal.advance(ql_d, ql.Period(n, ql.Days))
        return self._to_py(ql_result)


# ─────────────────────────────────────────────────────────────
# RebalanceWindow: 실행 시점 정책 판단
# ─────────────────────────────────────────────────────────────
class WindowDecision(Enum):
    """리밸런싱 실행 윈도우 판단 결과."""
    RUN_REBALANCE = auto()           # D 아침: 종목 선정 + 주문 실행
    SKIP_NOT_BUSINESS_DAY = auto()
    SKIP_NOT_REBALANCE_DAY = auto()  # 영업일이지만 D가 아님
    SKIP_OUT_OF_TIME_WINDOW = auto() # D이지만 시간대 밖



class RebalanceWindow:
    """리밸런싱 실행 윈도우 판단기.

    정책:
        D = max(직전 리밸 + interval일, 그 이후 첫 영업일)
        D 09:00 ~ 10:00 → RUN_REBALANCE (종목 선정 + 주문 실행을 한 번에)

    Args:
        calendar: KRX 영업일 캘린더
        clock: 현재 시각 제공자
        last_rebalance_date: 직전 성공 리밸런싱 일자 (DB에서 조회)
        rebalance_interval_days: 리밸런싱 주기 (기본 30일)
        start_time: 실행 윈도우 시작 시각. None이면 settings 디폴트.
        end_time: 실행 윈도우 종료 시각 (exclusive). None이면 settings 디폴트.
    """
    
    def __init__(
        self,
        calendar: KrxCalendar,
        clock: Clock,
        last_rebalance_date: date,
        rebalance_interval_days: int = 30,
        # 시간 윈도우는 None이면 settings 디폴트 사용 (테스트 시 주입 가능)
        start_time: time | None = None,
        end_time: time | None = None,
    ):
        self._calendar = calendar
        self._clock = clock
        self._last_rebalance_date = last_rebalance_date
        self._interval = rebalance_interval_days
        
        # 시간 윈도우 (DI 또는 settings 디폴트)
        self._start = start_time or time(
            rebalance_settings.REBALANCE_START_HOUR,
            rebalance_settings.REBALANCE_START_MINUTE,
        )
        self._end = end_time or time(
            rebalance_settings.REBALANCE_END_HOUR,
            rebalance_settings.REBALANCE_END_MINUTE,
        )
    
    
    def next_rebalance_date(self) -> date:
        """
        다음 리밸런싱 실행일(D) 계산.
        직전 리밸 + interval일을 기준으로 하되, 비영업일이면 다음 영업일로 보정.
        """
        target = self._last_rebalance_date + timedelta(days=self._interval)
        return self._calendar.adjust_to_next_business_day(target)
    
    
    def decide(self) -> WindowDecision:
        """현재 시각 기준으로 실행 윈도우 판단."""
        now = self._clock.now()
        today = now.date()
        current_time = now.time()
        
        D = self.next_rebalance_date()  # 다음 리밸런싱일
        
        # ⭐ case 1: D 아침(리밸런싱 실행 window)
        if today == D:
            if self._start <= current_time < self._end:
                return WindowDecision.RUN_REBALANCE
            return WindowDecision.SKIP_OUT_OF_TIME_WINDOW
        
        # ⭐ 그 외
        if not self._calendar.is_business_day(today):
            return WindowDecision.SKIP_NOT_BUSINESS_DAY
        return WindowDecision.SKIP_NOT_REBALANCE_DAY