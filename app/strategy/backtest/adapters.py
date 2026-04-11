import pandas as pd


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    데이터 소스별 포맷 차이를 표준화하는 계층

    목적:
    - provider마다 다른 컬럼명/형식 통일
    - 전략은 항상 동일한 입력 형식 사용하도록 보장
    """
    df = df.copy()

    # 예시:
    # df.rename(columns={"close": "Close"}, inplace=True)

    return df