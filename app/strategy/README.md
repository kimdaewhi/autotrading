# Strategy Module

## 개요
전략 모듈은 자동매매 시스템에서 **어떤 종목을 대상으로**, **어떤 시점에 매수/매도할지** 판단하고, 이를 실행 인프라에 전달하는 역할을 담당한다.

전략은 독립적으로 실행되며, 실행 결과(`TradeIntent`)를 Executor에 전달하는 구조로 설계되어 있다. 전략의 유형(포트폴리오 리밸런싱, 단일 매매 등)에 관계없이 동일한 인터페이스를 따른다.

---

## 모듈 구조

```
strategy/
  backtest/         백테스트
  filter/           필터링 (향후 사용)
  runtime/          실행 인프라 (Executor, OrderGenerator, PositionDiff)
  screener/         스크리너 (FScore 등)
  signals/          시그널 생성기 (Momentum, MACross, RSI 등)
  strategies/       완결형 전략 (스크리닝 → 시그널 → TradeIntent 변환)
  universe/         유니버스 필터 (시가총액 범위, 기본 필터 등)
```

### 핵심 구성요소

- **`signals/`** — OHLCV 데이터를 받아 BUY/SELL/HOLD 시그널을 생성하는 단위 모듈. `BaseSignal`을 상속하며, 백테스트에서도 직접 호출 가능하다.
- **`screener/`** — 재무 데이터 등을 기반으로 투자 유니버스를 선정하는 스크리너. `BaseScreener`를 상속한다.
- **`strategies/`** — 스크리너와 시그널을 조합한 완결형 전략. `BaseStrategy`를 상속하며, `execute()` 호출 시 `StrategyResult(orders=[TradeIntent, ...])`를 반환한다.
- **`runtime/`** — 전략 실행 결과를 받아 실제 주문을 처리하는 실행 인프라. `BaseExecutor`를 상속한 Executor가 전략 유형(`strategy_type`)에 따라 라우팅된다.

---

## 실행 흐름

### 전략 실행 파이프라인

```
Strategy.execute()          "무엇을 할지" 결정
    ├── Screener.screen()       유니버스 선정
    ├── Signal.generate_signal()  매매 시그널 생성
    └── TradeIntent[] 반환       매매 의도 표현
            │
            ▼
Executor.submit()           "어떻게 실행할지" 처리
    ├── 계좌 조회
    ├── 포지션 diff 계산
    ├── 주문 생성 + Celery 큐잉
    └── 체결 대기 + 상태 추적
```

### 전략 유형별 Executor 라우팅

| 전략 유형 | Executor | 설명 |
|-----------|----------|------|
| `REBALANCE` | `RebalanceExecutor` | 포트폴리오 리밸런싱 (diff 계산 → 매도/매수) |
| `DIRECT_TRADE` | `DirectTradeExecutor` | 단일 종목 즉시 매매 (향후 구현) |

### 현재 구현된 전략

**PiotroskiMomentumStrategy** (`strategies/piotroski_momentum_strategy.py`)
- F-Score 스크리닝 → Dual Momentum 시그널 → 균등 비중 TradeIntent 변환
- `strategy_type = REBALANCE`

---

## 전략 설계 원칙

### 1. 전략은 독립 모듈
전략은 실행 방식(리밸런싱, 즉시 매매 등)에 종속되지 않는다. `BaseStrategy.execute()`를 구현하고 `TradeIntent`를 반환하면 어떤 Executor에서든 처리할 수 있다.

### 2. 전략과 실행의 분리
전략은 "무엇을 사고/팔지"만 결정하고, 브로커 주문 API를 직접 호출하지 않는다. 주문 실행 책임은 Executor → OrderGenerator → Celery Worker로 분리하여 안정성과 추적 가능성을 확보한다.

### 3. 시그널 재사용
`signals/`의 시그널 생성기는 백테스트와 실전 매매 모두에서 동일하게 사용된다. `BaseStrategy.execute()` 내부에서 `generate_signal()`을 호출하므로, 시그널 로직은 한 곳에만 존재한다.

### 4. 의존성 주입
전략이 필요로 하는 스크리너, 시그널, 데이터 제공자는 `__init__`에서 DI로 주입받는다. `execute()`는 런타임 파라미터(year 등)만 받는다.

### 5. 전략은 상태를 인지해야 함
실시간 전략은 단순 조건식만으로 동작하지 않는다. 현재 보유 여부, 미체결 주문 존재 여부, 당일 진입 횟수, 장 운영 상태 등을 함께 고려해야 한다.

---

## 새 전략 추가 방법

1. `strategies/` 폴더에 새 파일 생성
2. `BaseStrategy`를 상속하고 `strategy_type`, `generate_signal()`, `execute()` 구현
3. `__init__`에서 필요한 의존성(스크리너, 시그널, 필터 등)을 DI로 주입
4. `execute()`에서 `StrategyResult(orders=[TradeIntent, ...])`를 반환
5. 새 전략 유형이면 `runtime/`에 해당 Executor 추가 + `executor_registry.py`에 라우팅 등록

```python
class MyNewStrategy(BaseStrategy):
    strategy_type = StrategyType.REBALANCE  # 또는 DIRECT_TRADE

    def __init__(self, screener, signal, data_provider):
        self.screener = screener
        self.signal = signal
        self.data_provider = data_provider

    def generate_signal(self, data):
        return self.signal.generate_signal(data)

    async def execute(self, year: int, **kwargs) -> StrategyResult:
        # 스크리닝 → 데이터 로딩 → 시그널 → TradeIntent 변환
        ...
        return StrategyResult(
            strategy_type=self.strategy_type,
            strategy_name=self.__class__.__name__,
            orders=[TradeIntent(...)],
        )
```

---

## 향후 확장 방향

### 실시간 매매 전략
현재는 배치 기반(리밸런싱) 전략이 구현되어 있으나, 향후 실시간 매매 전략도 동일한 구조 위에 확장할 수 있다.

- 과거 데이터 기반 당일 타깃 종목 선정
- 선정 종목 실시간 WebSocket 데이터 구독
- 장중 전략 조건 지속 평가 → 시그널 생성
- `DirectTradeExecutor`를 통한 즉시 주문 실행

### 기타 확장
- 복수 전략 동시 실행 + 전략별 자본 배분 (#7 보류 중)
- 이벤트 드리븐 전략 (LLM API 활용)
- 전략별 성과 기록 및 비교
- 손절/익절/트레일링 스탑 정책
- 분봉 실시간 집계