import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import io
import var

base_dir = "logs"
logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
)
logger = logging.getLogger()
log_file_path = os.path.join(os.getcwd(), base_dir, "logger.log")
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
fileHandler = TimedRotatingFileHandler(
    log_file_path, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)
consoleHandler = logging.StreamHandler()
if hasattr(sys.stdout, "readable") and sys.stdout.readable():
    consoleHandler.stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
else:
    consoleHandler.stream = io.StringIO()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)
logger.setLevel(level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.ERROR)
