from __future__ import annotations

import inspect
import typing

from .._content import ByteStream
from .._models import Request, Response
from .base import AsyncBaseTransport, BaseTransport

SyncHandler = typing.Callable[[Request], Response]
AsyncHandler = typing.Callable[[Request], typing.Coroutine[None, None, Response]]


__all__ = ["MockTransport"]


def _reopen_response(response: Response) -> Response:
    """
    Responses built with `content=`/`text=`/`json=` are read and closed as soon
    as they are constructed. Return the response to its "unread" state so that
    the client consumes it through its own stream wrapper, which is what sets
    `response.elapsed` and runs the usual close handling.
    """
    if response.is_closed and isinstance(response.stream, ByteStream):
        response.is_closed = False
        response.is_stream_consumed = False
        response.__dict__.pop("_content", None)
        response.__dict__.pop("_decoder", None)
    return response


class MockTransport(AsyncBaseTransport, BaseTransport):
    def __init__(self, handler: SyncHandler | AsyncHandler) -> None:
        self.handler = handler

    def handle_request(
        self,
        request: Request,
    ) -> Response:
        request.read()
        response = self.handler(request)
        if not isinstance(response, Response):
            if inspect.isawaitable(response):
                close = getattr(response, "close", None)
                if close is not None:
                    close()
                raise TypeError("Cannot use an async handler in a sync Client")
            raise TypeError(
                "MockTransport handler must return an httpx.Response, "
                f"got {type(response).__name__}."
            )
        return _reopen_response(response)

    async def handle_async_request(
        self,
        request: Request,
    ) -> Response:
        await request.aread()
        response = self.handler(request)

        # Allow handler to *optionally* be an `async` function.
        # If it is, then the `response` variable need to be awaited to actually
        # return the result.

        if not isinstance(response, Response):
            if not inspect.isawaitable(response):
                raise TypeError(
                    "MockTransport handler must return an httpx.Response or an "
                    f"awaitable resolving to one, got {type(response).__name__}."
                )
            response = await response
            if not isinstance(response, Response):
                raise TypeError(
                    "MockTransport async handler must return an httpx.Response, "
                    f"got {type(response).__name__}."
                )

        return _reopen_response(response)
