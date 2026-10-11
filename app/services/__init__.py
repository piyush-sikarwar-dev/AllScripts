"""Services: one per chart area. They merge sources, decode codes, format values and return
Pydantic view models. Repository calls (synchronous) run in worker threads via `call()`.
"""

from collections.abc import Callable
from functools import partial

import anyio


class NotFoundError(Exception):
    """The requested patient / record does not exist (rendered as 404)."""


async def call[T](fn: Callable[..., T], *args: object, **kwargs: object) -> T:
    """Run a synchronous repository function in a worker thread."""
    return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))
