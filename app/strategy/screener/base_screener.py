from abc import ABC, abstractmethod


class BaseScreener(ABC):

    @abstractmethod
    def screen(self, date: str) -> list[str]:
        """
        특정 시점 기준으로 투자 유니버스 종목 코드 리스트 반환
        """
        pass