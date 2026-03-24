RETRACKING_INTERVAL_SECONDS = 1     # 초기 재추적 간격(초)
MAX_RETRACKING_COUNT = 30           # (deprecated) 과거 고정 루프 방식 최대 재추적 횟수

# 주문 추적은 "짧은 구간 집중 조회 + 이후 성긴 조회" 전략으로 운용한다.
# KIS 체결조회 반영 지연이 수초~수분 단위로 발생할 수 있어, 고정 횟수보다
# 경과 시간을 기준으로 추적 윈도우를 관리한다.
ORDER_TRACKING_FAST_WINDOW_SECONDS = 90       # 최초 집중 추적 구간(초)
ORDER_TRACKING_MAX_WINDOW_SECONDS = 1800      # 총 추적 허용 구간(초, 30분)
ORDER_TRACKING_SLOW_INTERVAL_SECONDS = 60     # 느린 구간 재조회 간격(초)

HTTP_RETRY_COUNT = 3                # HTTP 요청 재시도 횟수
