import pytest

from app.market.provider.fdr_provider import FDRMarketDataProvider


@pytest.fixture
def provider():
    return FDRMarketDataProvider()


def test_get_stock_list(provider):
    df = provider.get_stock_list()

    assert not df.empty
    assert "code" in df.columns
    assert "name" in df.columns
    assert "market" in df.columns


def test_get_ohlcv(provider):
    df = provider.get_ohlcv("005930", "2025-01-01", "2025-01-10")

    assert not df.empty
    assert "Open" in df.columns
    assert "High" in df.columns
    assert "Low" in df.columns
    assert "Close" in df.columns
    assert "Volume" in df.columns