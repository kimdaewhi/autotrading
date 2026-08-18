from fastapi import APIRouter, Depends

from app.market.provider.fdr_provider import FDRMarketDataProvider
from app.schemas.market.market import MarketIndexRead
from app.services.market.market_service import MarketService

router = APIRouter()


def get_market_service() -> MarketService:
    return MarketService(provider=FDRMarketDataProvider())


@router.get("/market-summary", response_model=list[MarketIndexRead], description="주요시장 지수 조회")
def get_market_summary(service: MarketService = Depends(get_market_service)) -> list[MarketIndexRead]:
    return service.get_market_summary()