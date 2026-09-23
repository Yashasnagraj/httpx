from __future__ import annotations

import io
import itertools
import sys
import typing
from urllib.parse import unquote_to_bytes

from .._models import Request, Response
from .._types import SyncByteStream
from .base import BaseTransport

if typing.TYPE_CHECKING:
    from _typeshed import OptExcInfo  # pragma: no cover
    from _typeshed.wsgi import WSGIApplication  # pragma: no cover

_T = typing.TypeVar("_T")


__all__ = ["WSGITransport"]


def _skip_leading_empty_chunks(body: typing.Iterable[_T]) -> typing.Iterable[_T]:
    body = iter(body)
    for chunk in body:
        if chunk:
            return itertools.chain([chunk], body)
    return []


def _wsgi_native_string(value: str | bytes) -> str:
    """
    Return a PEP 3333 "native string": the percent-decoded, UTF-8 encoded
    bytes of a URL path, decoded as latin-1.
    """
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return unquote_to_bytes(raw).decode("latin-1")


class WSGIByteStream(SyncByteStream):
    def __init__(
        self, result: typing.Iterable[bytes], written: list[bytes] | None = None
    ) -> None:
        self._close = getattr(result, "close", None)
        # Data passed to the `write()` callable returned by `start_response`.
        # It must be transmitted ahead of any data yielded by the iterable.
        self._written = [] if written is None else written
        self._result = _skip_leading_empty_chunks(result)

    def _flush_written(self) -> typing.Iterator[bytes]:
        while self._written:
            yield self._written.pop(0)

    def __iter__(self) -> typing.Iterator[bytes]:
        for part in self._result:
            yield from self._flush_written()
            yield part
        yield from self._flush_written()

    def close(self) -> None:
        if self._close is not None:
            self._close()


class WSGITransport(BaseTransport):
    """
    A custom transport that handles sending requests directly to an WSGI app.
    The simplest way to use this functionality is to use the `app` argument.

    ```
    client = httpx.Client(app=app)
    ```

    Alternatively, you can setup the transport instance explicitly.
    This allows you to include any additional configuration arguments specific
    to the WSGITransport class:

    ```
    transport = httpx.WSGITransport(
        app=app,
        script_name="/submount",
        remote_addr="1.2.3.4"
    )
    client = httpx.Client(transport=transport)
    ```

    Arguments:

    * `app` - The WSGI application.
    * `raise_app_exceptions` - Boolean indicating if exceptions in the application
       should be raised. Default to `True`. Can be set to `False` for use cases
       such as testing the content of a client 500 response.
    * `script_name` - The root path on which the WSGI application should be mounted.
    * `remote_addr` - A string indicating the client IP of incoming requests.
    ```
    """

    def __init__(
        self,
        app: WSGIApplication,
        raise_app_exceptions: bool = True,
        script_name: str = "",
        remote_addr: str = "127.0.0.1",
        wsgi_errors: typing.TextIO | None = None,
    ) -> None:
        self.app = app
        self.raise_app_exceptions = raise_app_exceptions
        self.script_name = script_name
        self.remote_addr = remote_addr
        self.wsgi_errors = wsgi_errors

    def handle_request(self, request: Request) -> Response:
        request.read()
        wsgi_input = io.BytesIO(request.content)

        port = request.url.port or {"http": 80, "https": 443}[request.url.scheme]
        raw_path = request.url.raw_path.split(b"?")[0]
        environ: dict[str, typing.Any] = {
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": request.url.scheme,
            "wsgi.input": wsgi_input,
            # The full request body has been buffered into `wsgi.input`, so the
            # app may read it to EOF without relying on `CONTENT_LENGTH`.
            "wsgi.input_terminated": True,
            "wsgi.errors": self.wsgi_errors or sys.stderr,
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "REQUEST_METHOD": request.method,
            "SCRIPT_NAME": _wsgi_native_string(self.script_name),
            "PATH_INFO": _wsgi_native_string(raw_path),
            "QUERY_STRING": request.url.query.decode("ascii"),
            "SERVER_NAME": request.url.host,
            "SERVER_PORT": str(port),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "REMOTE_ADDR": self.remote_addr,
        }
        for header_key, header_value in request.headers.raw:
            key = header_key.decode("latin-1").upper().replace("-", "_")
            if key == "TRANSFER_ENCODING":
                # The body is fully buffered, so it is never chunked from the
                # app's point of view.
                continue
            if key not in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                key = "HTTP_" + key
            environ[key] = header_value.decode("latin-1")
        if request.content:
            environ["CONTENT_LENGTH"] = str(len(request.content))

        seen_status = None
        seen_response_headers = None
        seen_exc_info = None
        written: list[bytes] = []

        def start_response(
            status: str,
            response_headers: list[tuple[str, str]],
            exc_info: OptExcInfo | None = None,
        ) -> typing.Callable[[bytes], typing.Any]:
            nonlocal seen_status, seen_response_headers, seen_exc_info
            seen_status = status
            seen_response_headers = response_headers
            seen_exc_info = exc_info
            return written.append

        result = self.app(environ, start_response)

        stream = WSGIByteStream(result, written)

        assert seen_status is not None
        assert seen_response_headers is not None
        if seen_exc_info and seen_exc_info[0] and self.raise_app_exceptions:
            try:
                raise seen_exc_info[1]
            finally:
                stream.close()

        status_code = int(seen_status.split()[0])
        headers = [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in seen_response_headers
        ]

        return Response(status_code, headers=headers, stream=stream)
