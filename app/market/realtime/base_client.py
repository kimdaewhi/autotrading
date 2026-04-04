from abc import ABC, abstractmethod
from typing import Any


class BaseRealtimeClient(ABC):
    """
    실시간 시세 클라이언트 인터페이스
        - connect / disconnect: WebSocket 연결 생명주기
        - subscribe / unsubscribe: 종목 구독 관리
        - on_message: 수신 메시지 처리 (구현체에서 파싱 등 담당)
        - start: 연결 + 수신 루프 실행
    """

    @abstractmethod
    async def connect(self) -> None:
        """WebSocket 연결"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """WebSocket 연결 종료"""
        pass

    @abstractmethod
    async def subscribe(self, stock_code: str) -> None:
        """종목 실시간 데이터 구독"""
        pass

    @abstractmethod
    async def unsubscribe(self, stock_code: str) -> None:
        """종목 실시간 데이터 구독 해제"""
        pass

    @abstractmethod
    async def on_message(self, message: Any) -> None:
        """수신 메시지 처리"""
        pass

    @abstractmethod
    async def start(self) -> None:
        """연결 및 메시지 수신 루프 실행"""
        pass