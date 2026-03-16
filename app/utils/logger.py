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

        return f"{emoji}  {time}  [{module}]\t{record.getMessage()}"



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

    return logger