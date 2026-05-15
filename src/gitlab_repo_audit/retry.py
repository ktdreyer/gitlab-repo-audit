"""Retry decorator for network-level errors below python-gitlab's HTTP retry layer."""

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

import requests

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                ) as e:
                    if attempt >= max_retries:
                        logger.error("Network error after %d attempts: %s", max_retries + 1, e)
                        raise
                    delay = min(base_delay * (2**attempt), max_delay)
                    logger.warning("Network error (attempt %d/%d): %s", attempt + 1, max_retries + 1, e)
                    time.sleep(delay)
            raise RuntimeError("Unexpected retry loop exit")

        return cast(F, wrapper)

    return decorator
