from app.schemas.kis import DomesticStockOrderResponse


class TradeService:
    def __init__(self, kis_order):
        self.kis_order = kis_order

    async def buy_domestic_stock(self, stock_code: str, quantity: str, price: str, access_token: str) -> DomesticStockOrderResponse:
        return await self.kis_order.buy_domestic_stock(stock_code, quantity, price, access_token)

    async def sell_domestic_stock(self, stock_code: str, quantity: str, price: str, access_token: str) -> DomesticStockOrderResponse:
        return await self.kis_order.sell_domestic_stock(stock_code, quantity, price, access_token)