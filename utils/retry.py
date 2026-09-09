import asyncio
from functools import wraps
import time
from typing import Callable, Any, Tuple, Type
from utils.logger import get_logger

logger = get_logger("retry_handler")


def retry_sync(
    max_attempts: int = 3,
    delays: Tuple[float, ...] = (2.0, 4.0, 8.0),
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Synchronous retry decorator with exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_err: Exception = Exception("Unknown error")
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[RetrySync] Failed after {max_attempts} attempts for {func.__name__}: {e}",
                            extra={"function": func.__name__, "attempt": attempt},
                        )
                        raise
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else delays[-1]
                    logger.warning(
                        f"[RetrySync] Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. Retrying in {delay}s...",
                        extra={"function": func.__name__, "attempt": attempt, "delay": delay},
                    )
                    time.sleep(delay)
            raise last_err
        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    delays: Tuple[float, ...] = (2.0, 4.0, 8.0),
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Asynchronous retry decorator with exponential backoff.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_err: Exception = Exception("Unknown error")
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt == max_attempts:
                        logger.error(
                            f"[RetryAsync] Failed after {max_attempts} attempts for {func.__name__}: {e}",
                            extra={"function": func.__name__, "attempt": attempt},
                        )
                        raise
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else delays[-1]
                    logger.warning(
                        f"[RetryAsync] Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. Retrying in {delay}s...",
                        extra={"function": func.__name__, "attempt": attempt, "delay": delay},
                    )
                    await asyncio.sleep(delay)
            raise last_err
        return wrapper
    return decorator
