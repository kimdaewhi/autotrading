"""KRX 영업일 캘린더 및 리밸런싱 윈도우 단위 테스트."""

from datetime import date, datetime, time

import pytest

from app.utils.market_calendar import (
    FixedClock,
    KrxCalendar,
    RebalanceWindow,
    SystemClock,
    WindowDecision,
    KST,
)


# ═════════════════════════════════════════════════════════════
# Part 1: KrxCalendar
# ═════════════════════════════════════════════════════════════
class TestKrxCalendarBusinessDay:
    """is_business_day 동작 검증."""

    @pytest.fixture
    def calendar(self) -> KrxCalendar:
        return KrxCalendar()

    def test_평일은_영업일이다(self, calendar):
        # 2026-05-04 (월) - 평범한 평일
        assert calendar.is_business_day(date(2026, 5, 4)) is True

    def test_주말은_영업일이_아니다(self, calendar):
        assert calendar.is_business_day(date(2026, 5, 2)) is False  # 토
        assert calendar.is_business_day(date(2026, 5, 3)) is False  # 일

    def test_신정은_영업일이_아니다(self, calendar):
        assert calendar.is_business_day(date(2026, 1, 1)) is False

    def test_근로자의_날은_영업일이_아니다(self, calendar):
        # 2026-05-01 (금)
        assert calendar.is_business_day(date(2026, 5, 1)) is False

    def test_어린이날은_영업일이_아니다(self, calendar):
        # 2026-05-05 (화)
        assert calendar.is_business_day(date(2026, 5, 5)) is False

    def test_대체공휴일도_영업일이_아니다(self, calendar):
        # 2026-08-15 광복절(토) → 8/17(월) 대체공휴일
        assert calendar.is_business_day(date(2026, 8, 17)) is False

    def test_연말_폐장일은_영업일이_아니다(self, calendar):
        # 2026-12-31
        assert calendar.is_business_day(date(2026, 12, 31)) is False


class TestKrxCalendarExtraHolidays:
    """KRX_EXTRA_HOLIDAYS 보정 동작 검증 (제헌절 등)."""

    def test_제헌절은_extra_holidays로_보정되어_영업일이_아니다(self):
        """기본 KrxCalendar는 KRX_EXTRA_HOLIDAYS 자동 적용."""
        calendar = KrxCalendar()
        assert calendar.is_business_day(date(2026, 7, 17)) is False

    def test_extra_holidays_미주입시_quantlib_기본_동작(self):
        """빈 리스트로 초기화해도 QuantLib 기본 휴일은 정상 동작."""
        calendar = KrxCalendar(extra_holidays=[])
        # QuantLib이 알고 있는 휴일은 여전히 휴일
        assert calendar.is_business_day(date(2026, 5, 5)) is False  # 어린이날
        assert calendar.is_business_day(date(2026, 1, 1)) is False  # 신정
        # 평일은 평일
        assert calendar.is_business_day(date(2026, 5, 4)) is True

    def test_사용자_지정_휴일_등록_가능(self):
        """임의 날짜를 휴일로 등록할 수 있다."""
        custom_holiday = date(2026, 6, 15)
        calendar = KrxCalendar(extra_holidays=[custom_holiday])
        assert calendar.is_business_day(custom_holiday) is False


class TestKrxCalendarBusinessDayNavigation:
    """next/previous/adjust 동작 검증."""

    @pytest.fixture
    def calendar(self) -> KrxCalendar:
        return KrxCalendar()

    def test_next_business_day_평일은_다음_평일로(self, calendar):
        # 5/4(월) → 5/6(수). 5/5(화)는 어린이날
        assert calendar.next_business_day(date(2026, 5, 4)) == date(2026, 5, 6)

    def test_next_business_day_금요일은_다음주_월요일로(self, calendar):
        # 5/8(금) → 5/11(월)
        assert calendar.next_business_day(date(2026, 5, 8)) == date(2026, 5, 11)

    def test_previous_business_day_평일은_직전_평일로(self, calendar):
        # 5/6(수) → 5/4(월). 5/5(화)는 어린이날
        assert calendar.previous_business_day(date(2026, 5, 6)) == date(2026, 5, 4)

    def test_adjust_to_next_영업일이면_그대로(self, calendar):
        # 5/4(월)은 영업일 → 보정 없이 그대로
        assert calendar.adjust_to_next_business_day(date(2026, 5, 4)) == date(2026, 5, 4)

    def test_adjust_to_next_비영업일은_다음_영업일로(self, calendar):
        # 5/5(화) 어린이날 → 5/6(수)
        assert calendar.adjust_to_next_business_day(date(2026, 5, 5)) == date(2026, 5, 6)

    def test_adjust_to_next_주말은_월요일로(self, calendar):
        # 5/2(토) → 5/4(월)
        assert calendar.adjust_to_next_business_day(date(2026, 5, 2)) == date(2026, 5, 4)


# ═════════════════════════════════════════════════════════════
# Part 2: RebalanceWindow
# ═════════════════════════════════════════════════════════════
class TestRebalanceWindowDateCalculation:
    """next_rebalance_date 계산 로직."""

    @pytest.fixture
    def calendar(self) -> KrxCalendar:
        return KrxCalendar()

    def _make_window(
        self,
        calendar: KrxCalendar,
        last_date: date,
        now: datetime,
        interval: int = 30,
    ) -> RebalanceWindow:
        return RebalanceWindow(
            calendar=calendar,
            clock=FixedClock(fixed_now=now),
            last_rebalance_date=last_date,
            rebalance_interval_days=interval,
        )

    def test_30일_후가_영업일이면_그대로(self, calendar):
        # 2026-04-15(수) + 30일 = 2026-05-15(금) → 영업일
        window = self._make_window(
            calendar=calendar,
            last_date=date(2026, 4, 15),
            now=datetime(2026, 4, 16, 10, 0, tzinfo=KST),
        )
        assert window.next_rebalance_date() == date(2026, 5, 15)

    def test_30일_후가_비영업일이면_다음_영업일로_보정(self, calendar):
        # 2026-04-05(일) + 30일 = 2026-05-05(어린이날) → 5/6(수)로 보정 기대
        window = self._make_window(
            calendar=calendar,
            last_date=date(2026, 4, 5),
            now=datetime(2026, 4, 6, 10, 0, tzinfo=KST),
        )
        assert window.next_rebalance_date() == date(2026, 5, 6)


class TestRebalanceWindowDecision:
    """decide() 정책 판단 로직.

    기준 시나리오: last=2026-04-15, D=2026-05-15(금)
    """

    LAST_REBALANCE = date(2026, 4, 15)
    D = date(2026, 5, 15)

    @pytest.fixture
    def calendar(self) -> KrxCalendar:
        return KrxCalendar()

    def _make_window(self, calendar: KrxCalendar, now: datetime) -> RebalanceWindow:
        return RebalanceWindow(
            calendar=calendar,
            clock=FixedClock(fixed_now=now),
            last_rebalance_date=self.LAST_REBALANCE,
        )

    # ── RUN_REBALANCE (D 09:00 ~ 10:00) ──
    def test_D_아침_9시_정각이면_리밸런싱_실행(self, calendar):
        now = datetime(2026, 5, 15, 9, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.RUN_REBALANCE

    def test_D_아침_9시_30분이면_리밸런싱_실행(self, calendar):
        now = datetime(2026, 5, 15, 9, 30, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.RUN_REBALANCE

    def test_D_아침_9시_59분이면_리밸런싱_실행(self, calendar):
        now = datetime(2026, 5, 15, 9, 59, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.RUN_REBALANCE

    def test_D_아침_10시_정각은_경계값으로_제외(self, calendar):
        """10:00 정각은 윈도우 종료 → SKIP."""
        now = datetime(2026, 5, 15, 10, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_OUT_OF_TIME_WINDOW

    def test_D_아침_8시_59는_시간윈도우_밖(self, calendar):
        now = datetime(2026, 5, 15, 8, 59, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_OUT_OF_TIME_WINDOW

    def test_D_오후는_시간윈도우_밖(self, calendar):
        now = datetime(2026, 5, 15, 14, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_OUT_OF_TIME_WINDOW

    # ── SKIP_NOT_BUSINESS_DAY ──
    def test_주말은_영업일_아님(self, calendar):
        # 2026-05-16 (토)
        now = datetime(2026, 5, 16, 10, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_NOT_BUSINESS_DAY

    def test_공휴일은_영업일_아님(self, calendar):
        # 2026-05-25 (월) 부처님오신날 대체공휴일
        now = datetime(2026, 5, 25, 10, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_NOT_BUSINESS_DAY

    # ── SKIP_NOT_REBALANCE_DAY ──
    def test_영업일이지만_리밸_날짜가_아니면_스킵(self, calendar):
        # 2026-05-13(수): 영업일이지만 D가 아님
        now = datetime(2026, 5, 13, 10, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_NOT_REBALANCE_DAY

    def test_D_직전_영업일은_리밸_날짜_아님(self, calendar):
        """과거에는 D-1 저녁이 종목 선정 윈도우였으나, 통합 후엔 SKIP."""
        # 2026-05-14(목): D 직전 영업일
        now = datetime(2026, 5, 14, 19, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_NOT_REBALANCE_DAY

    def test_D_다음_영업일은_리밸_날짜_아님(self, calendar):
        # 2026-05-18(월): D(5/15) 다음 영업일
        now = datetime(2026, 5, 18, 10, 0, tzinfo=KST)
        window = self._make_window(calendar, now)
        assert window.decide() == WindowDecision.SKIP_NOT_REBALANCE_DAY


class TestRebalanceWindowTimeInjection:
    """시간 윈도우 DI 동작 검증."""

    def test_커스텀_시간윈도우_주입_가능(self):
        """settings 디폴트와 다른 시간을 주입할 수 있다."""
        calendar = KrxCalendar()
        # 커스텀: 실행 윈도우 = 10:00 ~ 10:30
        window = RebalanceWindow(
            calendar=calendar,
            clock=FixedClock(fixed_now=datetime(2026, 5, 15, 9, 30, tzinfo=KST)),
            last_rebalance_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        # 9:30은 커스텀 start(10:00)보다 이전 → SKIP
        assert window.decide() == WindowDecision.SKIP_OUT_OF_TIME_WINDOW

    def test_커스텀_시간윈도우_안에_들어오면_리밸런싱_실행(self):
        calendar = KrxCalendar()
        window = RebalanceWindow(
            calendar=calendar,
            clock=FixedClock(fixed_now=datetime(2026, 5, 15, 10, 15, tzinfo=KST)),
            last_rebalance_date=date(2026, 4, 15),
            start_time=time(10, 0),
            end_time=time(10, 30),
        )
        assert window.decide() == WindowDecision.RUN_REBALANCE


# ═════════════════════════════════════════════════════════════
# Part 3: 통합 시나리오 (대휘의 실제 케이스)
# ═════════════════════════════════════════════════════════════
class TestRealScenario_2026_04_15_to_05_15:
    """2026-04-15 첫 리밸 후 한 달 동안의 시간 흐름 검증.

    Phase 3 검증 시작일이 2026-04-15(수). 다음 리밸은 D=5/15(금).
    이 한 달 동안 매 시점에 decide()가 어떻게 반응하는지 끝까지 따라가본다.
    """

    LAST = date(2026, 4, 15)

    @pytest.fixture
    def calendar(self):
        return KrxCalendar()

    def _decide_at(self, calendar: KrxCalendar, now: datetime) -> WindowDecision:
        return RebalanceWindow(
            calendar=calendar,
            clock=FixedClock(fixed_now=now),
            last_rebalance_date=self.LAST,
        ).decide()

    def test_리밸_직후_4월_16일_평일_낮은_스킵(self, calendar):
        """리밸 다음날: 영업일이지만 리밸 날짜 아님."""
        decision = self._decide_at(
            calendar, datetime(2026, 4, 16, 10, 0, tzinfo=KST)
        )
        assert decision == WindowDecision.SKIP_NOT_REBALANCE_DAY

    def test_5월_연휴_5월_5일_어린이날은_비영업일_스킵(self, calendar):
        decision = self._decide_at(
            calendar, datetime(2026, 5, 5, 10, 0, tzinfo=KST)
        )
        assert decision == WindowDecision.SKIP_NOT_BUSINESS_DAY

    def test_D_직전일_5월_14일_저녁은_리밸_날짜_아님(self, calendar):
        """과거엔 D-1 저녁이 종목 선정 윈도우였으나 통합 후엔 SKIP."""
        decision = self._decide_at(
            calendar, datetime(2026, 5, 14, 19, 0, tzinfo=KST)
        )
        assert decision == WindowDecision.SKIP_NOT_REBALANCE_DAY

    def test_5월_15일_9시_5분은_리밸런싱_트리거(self, calendar):
        """D 시가 직후: 리밸런싱 실행."""
        decision = self._decide_at(
            calendar, datetime(2026, 5, 15, 9, 5, tzinfo=KST)
        )
        assert decision == WindowDecision.RUN_REBALANCE

    def test_5월_15일_9시_45분도_리밸런싱_트리거(self, calendar):
        """D 윈도우 후반부: 여전히 실행 가능."""
        decision = self._decide_at(
            calendar, datetime(2026, 5, 15, 9, 45, tzinfo=KST)
        )
        assert decision == WindowDecision.RUN_REBALANCE

    def test_5월_15일_장마감은_시간윈도우_스킵(self, calendar):
        """D이지만 10:00 이후: 시간윈도우 밖."""
        decision = self._decide_at(
            calendar, datetime(2026, 5, 15, 15, 0, tzinfo=KST)
        )
        assert decision == WindowDecision.SKIP_OUT_OF_TIME_WINDOW