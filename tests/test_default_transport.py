import gzip
import socket
import typing

import httpcore
import pytest

import httpx

SOCKET_OPTIONS = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]


@pytest.mark.parametrize(
    "transport_cls", [httpx.HTTPTransport, httpx.AsyncHTTPTransport]
)
@pytest.mark.parametrize(
    "proxy", ["http://localhost:8080", "https://localhost:8080", None]
)
def test_transport_options_are_passed_to_http_proxy_pool(transport_cls, proxy):
    """
    `retries`, `local_address`, `uds` and `socket_options` must not be dropped
    when an HTTP proxy is configured.
    """
    transport = transport_cls(
        proxy=proxy,
        retries=3,
        local_address="0.0.0.0",
        uds="/tmp/example.sock",
        socket_options=SOCKET_OPTIONS,
    )
    pool = transport._pool
    if proxy is None:
        assert isinstance(pool, (httpcore.ConnectionPool, httpcore.AsyncConnectionPool))
    else:
        assert isinstance(pool, (httpcore.HTTPProxy, httpcore.AsyncHTTPProxy))
    assert pool._retries == 3
    assert pool._local_address == "0.0.0.0"
    assert pool._uds == "/tmp/example.sock"
    assert pool._socket_options == SOCKET_OPTIONS


@pytest.mark.parametrize(
    "transport_cls", [httpx.HTTPTransport, httpx.AsyncHTTPTransport]
)
@pytest.mark.parametrize("proxy", ["socks5://localhost:1080", "socks5h://localhost"])
def test_retries_are_passed_to_socks_proxy_pool(transport_cls, proxy):
    transport = transport_cls(proxy=proxy, retries=3)
    pool = transport._pool
    assert isinstance(pool, (httpcore.SOCKSProxy, httpcore.AsyncSOCKSProxy))
    assert pool._retries == 3


@pytest.mark.parametrize(
    "transport_cls", [httpx.HTTPTransport, httpx.AsyncHTTPTransport]
)
def test_transport_requires_http1_or_http2(transport_cls):
    with pytest.raises(ValueError, match="Either http1 or http2 must be enabled"):
        transport_cls(http1=False, http2=False)


def test_transport_context_manager():
    with httpx.HTTPTransport() as transport:
        assert isinstance(transport._pool, httpcore.ConnectionPool)


@pytest.mark.anyio
async def test_async_transport_context_manager():
    async with httpx.AsyncHTTPTransport() as transport:
        assert isinstance(transport._pool, httpcore.AsyncConnectionPool)


# MockTransport


def test_mock_transport_response_elapsed():
    """
    See https://github.com/encode/httpx/issues/3712
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hello": "world"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = client.get("http://example.org/")

    assert response.json() == {"hello": "world"}
    assert response.is_closed
    assert response.elapsed.total_seconds() >= 0


def test_mock_transport_response_elapsed_with_stream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"streamed"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with client.stream("GET", "http://example.org/") as response:
            with pytest.raises(RuntimeError):
                response.elapsed  # noqa: B018
            response.read()

    assert response.text == "streamed"
    assert response.elapsed.total_seconds() >= 0


def test_mock_transport_response_elapsed_with_content_encoding():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=gzip.compress(b"compressed"),
            headers={"Content-Encoding": "gzip"},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = client.get("http://example.org/")

    assert response.text == "compressed"
    assert response.elapsed.total_seconds() >= 0


@pytest.mark.anyio
async def test_mock_transport_async_response_elapsed():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Hello, world!")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.get("http://example.org/")

    assert response.text == "Hello, world!"
    assert response.elapsed.total_seconds() >= 0


def test_mock_transport_sync_handler_returning_non_response():
    def handler(request: httpx.Request) -> typing.Any:
        return {"not": "a response"}

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TypeError, match="must return an httpx.Response"):
            client.get("http://example.org/")


def test_mock_transport_sync_client_with_async_handler():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)  # pragma: no cover

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TypeError, match="Cannot use an async handler"):
            client.get("http://example.org/")


@pytest.mark.anyio
async def test_mock_transport_async_handler_returning_non_awaitable():
    def handler(request: httpx.Request) -> typing.Any:
        return "not a response"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TypeError, match="must return an httpx.Response"):
            await client.get("http://example.org/")


@pytest.mark.anyio
async def test_mock_transport_async_handler_resolving_to_non_response():
    async def handler(request: httpx.Request) -> typing.Any:
        return "not a response"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TypeError, match="must return an httpx.Response"):
            await client.get("http://example.org/")
