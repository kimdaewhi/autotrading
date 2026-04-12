import logging
from datetime import datetime

LEVEL_EMOJI = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🔥",
}


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        time = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        emoji = LEVEL_EMOJI.get(record.levelname, "")
        module = record.name.split(".")[-1]
        message = record.getMessage()
        
        # 특정 로그 메시지에만 별도 이모지 부여
        if "주문 체결 완료" in message:
            emoji = "☑️"
        elif "주문 부분 체결" in message:
            emoji = "🔄"
        else:
            emoji = LEVEL_EMOJI.get(record.levelname, "")
        
        return f"{emoji}  {time}  [{module}]\t{message}"



def get_logger(name: str) -> logging.Logger:
    """
    모듈별로 구분된 Prettier 로그를 제공하는 로거를 반환
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(PrettyFormatter())

        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    
    elif len(logger.handlers) > 1:
        # fork 등으로 핸들러가 중복 등록된 경우 정리
        logger.handlers = [logger.handlers[0]]

    return logger