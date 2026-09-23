import typing as _typing

from .__version__ import __description__, __title__, __version__
from ._api import *
from ._auth import *
from ._client import *
from ._config import *
from ._content import *
from ._exceptions import *
from ._models import *
from ._status_codes import *
from ._transports import *
from ._types import *
from ._urls import *


class _LazyMain:
    """
    Entry point for the `httpx` command line client.

    The CLI depends on `click`, `rich` and `pygments`, which are slow to import
    and only needed when the command is actually run, so `httpx._main` is
    imported on first use rather than when `httpx` itself is imported.
    """

    @staticmethod
    def _resolve() -> _typing.Any:
        try:
            from ._main import main
        except ImportError:  # pragma: no cover
            return None
        return main

    def __call__(self, *args: _typing.Any, **kwargs: _typing.Any) -> _typing.Any:
        command = self._resolve()
        if command is None:  # pragma: no cover
            import sys

            print(
                "The httpx command line client could not run because the required "
                "dependencies were not installed.\nMake sure you've installed "
                "everything with: pip install 'httpx[cli]'"
            )
            sys.exit(1)
        return command(*args, **kwargs)

    def __getattr__(self, name: str) -> _typing.Any:
        # Forward attribute access (e.g. `.main`, used by `click.testing`) to
        # the underlying click command. Dunder lookups are answered locally so
        # that introspection doesn't trigger the import.
        if name.startswith("__"):
            raise AttributeError(name)
        command = self._resolve()
        if command is None:  # pragma: no cover
            raise AttributeError(name)
        return getattr(command, name)


if _typing.TYPE_CHECKING:  # pragma: no cover
    from ._main import main
else:
    main = _LazyMain()


__all__ = [
    "__description__",
    "__title__",
    "__version__",
    "ASGITransport",
    "AsyncBaseTransport",
    "AsyncByteStream",
    "AsyncClient",
    "AsyncHTTPTransport",
    "Auth",
    "BaseTransport",
    "BasicAuth",
    "ByteStream",
    "Client",
    "CloseError",
    "codes",
    "ConnectError",
    "ConnectTimeout",
    "CookieConflict",
    "Cookies",
    "create_ssl_context",
    "DecodingError",
    "delete",
    "DigestAuth",
    "FunctionAuth",
    "get",
    "head",
    "Headers",
    "HTTPError",
    "HTTPStatusError",
    "HTTPTransport",
    "InvalidURL",
    "Limits",
    "LocalProtocolError",
    "main",
    "MockTransport",
    "NetRCAuth",
    "NetworkError",
    "options",
    "patch",
    "PoolTimeout",
    "post",
    "ProtocolError",
    "Proxy",
    "ProxyError",
    "put",
    "QueryParams",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "request",
    "Request",
    "RequestError",
    "RequestNotRead",
    "Response",
    "ResponseNotRead",
    "stream",
    "StreamClosed",
    "StreamConsumed",
    "StreamError",
    "SyncByteStream",
    "Timeout",
    "TimeoutException",
    "TooManyRedirects",
    "TransportError",
    "UnsupportedProtocol",
    "URL",
    "USE_CLIENT_DEFAULT",
    "WriteError",
    "WriteTimeout",
    "WSGITransport",
]


__locals = locals()
for __name in __all__:
    if not __name.startswith("__"):
        setattr(__locals[__name], "__module__", "httpx")  # noqa
