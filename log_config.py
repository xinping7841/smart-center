"""
统一的日志基础设施。

环境变量：
  SMART_CENTER_LOG_LEVEL   日志级别，默认 INFO。可选 DEBUG / INFO / WARNING / ERROR。
  SMART_CENTER_LOG_FILE    日志输出文件，默认留空输出到 stderr（兼容 systemd journald）。
  SMART_CENTER_LOG_FORMAT  默认 "[{asctime}] {levelname:<7s} {name}:{lineno}  {message}"

用法：
  from log_config import get_logger
  logger = get_logger(__name__)
  logger.info("something happened")
  logger.warning("abnormal condition: %s", detail)
  logger.error("failed: %s", error, exc_info=True)
"""

import logging
import os
import sys
import time as _time

_LOG_FORMAT = str(os.environ.get(
    "SMART_CENTER_LOG_FORMAT",
    "[{asctime}] {levelname:<7s} {name}:{lineno}  {message}"
)).strip()

_LOG_DATE_FORMAT = str(os.environ.get(
    "SMART_CENTER_LOG_DATE_FORMAT",
    "%Y-%m-%d %H:%M:%S"
)).strip()

_LOG_LEVEL_NAME = str(os.environ.get("SMART_CENTER_LOG_LEVEL", "INFO")).strip().upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)

_LOG_FILE = str(os.environ.get("SMART_CENTER_LOG_FILE", "")).strip()

_initialized = False


def _init_logging():
    """初始化全局日志配置，仅执行一次。"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(_LOG_LEVEL)

    handler: logging.Handler
    if _LOG_FILE:
        handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT, style="{")
    handler.setFormatter(formatter)
    handler.setLevel(_LOG_LEVEL)

    if not any(isinstance(h, type(handler)) for h in root.handlers):
        root.addHandler(handler)

    for noisy in ("urllib3", "requests", "werkzeug", "modbus_tk", "paho", "pysnmp", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。首次调用会自动初始化全局日志配置。"""
    _init_logging()
    return logging.getLogger(name)


_log_once_cache: dict = {}
_log_once_lock = None


def _get_log_once_lock():
    import threading
    global _log_once_lock
    if _log_once_lock is None:
        _log_once_lock = threading.Lock()
    return _log_once_lock


def log_once(logger: logging.Logger, level: int, msg: str, *args):
    """节流日志：相同消息在短时间内只输出一次。
    
    适合放在频繁循环中、但不想刷屏的异常捕获位置。
    节流间隔由 SMART_CENTER_LOG_THROTTLE_SEC 控制，默认 30 秒。
    """
    throttle_sec = max(1.0, float(os.environ.get("SMART_CENTER_LOG_THROTTLE_SEC", "30") or 30))
    key = (id(logger), level, msg)
    now = _time.monotonic()
    with _get_log_once_lock():
        last = float(_log_once_cache.get(key, 0.0) or 0.0)
        if now - last < throttle_sec:
            return
        _log_once_cache[key] = now
    logger.log(level, msg, *args)
