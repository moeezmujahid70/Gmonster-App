import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import io

from runtime_paths import resolve_runtime_paths


def _log_directory():
    paths = resolve_runtime_paths(
        frozen=bool(getattr(sys, "frozen", False)),
        platform_name=sys.platform,
        executable=sys.executable,
        resource_dir=getattr(sys, "_MEIPASS", os.getcwd()),
        working_dir=os.getcwd(),
        local_app_data=os.environ.get(
            "LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local")
        ),
    )
    return paths.data_dir / "logs" / "gmonster"


base_dir = _log_directory()
logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"
)
logger = logging.getLogger()
log_file_path = base_dir / "logger.log"
os.makedirs(log_file_path.parent, exist_ok=True)
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
