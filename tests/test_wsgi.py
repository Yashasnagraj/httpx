from __future__ import annotations

import sys
import typing
import wsgiref.validate
from functools import partial
from io import StringIO
from urllib.parse import unquote

import pytest

import httpx

if typing.TYPE_CHECKING:  # pragma: no cover
    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment


def application_factory(output: typing.Iterable[bytes]) -> WSGIApplication:
    def application(environ, start_response):
        status = "200 OK"

        response_headers = [
            ("Content-type", "text/plain"),
        ]

        start_response(status, response_headers)

        for item in output:
            yield item

    return wsgiref.validate.validator(application)


def echo_body(
    environ: WSGIEnvironment, start_response: StartResponse
) -> typing.Iterable[bytes]:
    status = "200 OK"
    output = environ["wsgi.input"].read()

    response_headers = [
        ("Content-type", "text/plain"),
    ]

    start_response(status, response_headers)

    return [output]


def echo_body_with_response_stream(
    environ: WSGIEnvironment, start_response: StartResponse
) -> typing.Iterable[bytes]:
    status = "200 OK"

    response_headers = [("Content-Type", "text/plain")]

    start_response(status, response_headers)

    def output_generator(f: typing.IO[bytes]) -> typing.Iterator[bytes]:
        while True:
            output = f.read(2)
            if not output:
                break
            yield output

    return output_generator(f=environ["wsgi.input"])


def raise_exc(
    environ: WSGIEnvironment,
    start_response: StartResponse,
    exc: type[Exception] = ValueError,
) -> typing.Iterable[bytes]:
    status = "500 Server Error"
    output = b"Nope!"

    response_headers = [
        ("Content-type", "text/plain"),
    ]

    try:
        raise exc()
    except exc:
        exc_info = sys.exc_info()
        start_response(status, response_headers, exc_info)

    return [output]


def log_to_wsgi_log_buffer(environ, start_response):
    print("test1", file=environ["wsgi.errors"])
    environ["wsgi.errors"].write("test2")
    return echo_body(environ, start_response)


def test_wsgi():
    transport = httpx.WSGITransport(app=application_factory([b"Hello, World!"]))
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == "Hello, World!"


def test_wsgi_upload():
    transport = httpx.WSGITransport(app=echo_body)
    client = httpx.Client(transport=transport)
    response = client.post("http://www.example.org/", content=b"example")
    assert response.status_code == 200
    assert response.text == "example"


def test_wsgi_upload_with_response_stream():
    transport = httpx.WSGITransport(app=echo_body_with_response_stream)
    client = httpx.Client(transport=transport)
    response = client.post("http://www.example.org/", content=b"example")
    assert response.status_code == 200
    assert response.text == "example"


def test_wsgi_exc():
    transport = httpx.WSGITransport(app=raise_exc)
    client = httpx.Client(transport=transport)
    with pytest.raises(ValueError):
        client.get("http://www.example.org/")


def test_wsgi_http_error():
    transport = httpx.WSGITransport(app=partial(raise_exc, exc=RuntimeError))
    client = httpx.Client(transport=transport)
    with pytest.raises(RuntimeError):
        client.get("http://www.example.org/")


def test_wsgi_generator():
    output = [b"", b"", b"Some content", b" and more content"]
    transport = httpx.WSGITransport(app=application_factory(output))
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == "Some content and more content"


def test_wsgi_generator_empty():
    output = [b"", b"", b"", b""]
    transport = httpx.WSGITransport(app=application_factory(output))
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == ""


def test_logging():
    buffer = StringIO()
    transport = httpx.WSGITransport(app=log_to_wsgi_log_buffer, wsgi_errors=buffer)
    client = httpx.Client(transport=transport)
    response = client.post("http://www.example.org/", content=b"example")
    assert response.status_code == 200  # no errors
    buffer.seek(0)
    assert buffer.read() == "test1\ntest2"


@pytest.mark.parametrize(
    "url, expected_server_port",
    [
        pytest.param("http://www.example.org", "80", id="auto-http"),
        pytest.param("https://www.example.org", "443", id="auto-https"),
        pytest.param("http://www.example.org:8000", "8000", id="explicit-port"),
    ],
)
def test_wsgi_server_port(url: str, expected_server_port: str) -> None:
    """
    SERVER_PORT is populated correctly from the requested URL.
    """
    hello_world_app = application_factory([b"Hello, World!"])
    server_port: str | None = None

    def app(environ, start_response):
        nonlocal server_port
        server_port = environ["SERVER_PORT"]
        return hello_world_app(environ, start_response)

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get(url)
    assert response.status_code == 200
    assert response.text == "Hello, World!"
    assert server_port == expected_server_port


def test_wsgi_server_protocol():
    server_protocol = None

    def app(environ, start_response):
        nonlocal server_protocol
        server_protocol = environ["SERVER_PROTOCOL"]
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"success"]

    transport = httpx.WSGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.text == "success"
    assert server_protocol == "HTTP/1.1"


def test_wsgi_chunked_request_body_is_buffered():
    """
    A streamed request body is fully buffered into `wsgi.input`, so the app is
    told the content length rather than seeing `Transfer-Encoding: chunked`.
    """
    seen_environ: dict[str, typing.Any] = {}

    def app(environ, start_response):
        seen_environ.update(environ)
        body = environ["wsgi.input"].read()
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [body]

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.post("http://www.example.org/", content=iter([b"ex", b"ample"]))
    assert response.status_code == 200
    assert response.text == "example"
    assert seen_environ["CONTENT_LENGTH"] == "7"
    assert seen_environ["wsgi.input_terminated"] is True
    assert "HTTP_TRANSFER_ENCODING" not in seen_environ


def test_wsgi_no_content_length_without_body():
    seen_environ: dict[str, typing.Any] = {}

    def app(environ, start_response):
        seen_environ.update(environ)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert "CONTENT_LENGTH" not in seen_environ


@pytest.mark.parametrize(
    "path, expected_path_info",
    [
        pytest.param("/café", "/caf\xc3\xa9", id="latin-1-range"),
        pytest.param("/tick/✓", "/tick/\xe2\x9c\x93", id="outside-latin-1"),
        pytest.param("/a%20b", "/a b", id="percent-encoded"),
        pytest.param("/plain", "/plain", id="ascii"),
    ],
)
def test_wsgi_path_info_is_native_string(path: str, expected_path_info: str) -> None:
    """
    PEP 3333 requires `PATH_INFO` to be the percent-decoded UTF-8 bytes of the
    path, decoded as latin-1 (a "native string"), so that frameworks can
    recover the original path with `.encode("latin-1").decode("utf-8")`.
    """
    seen_environ: dict[str, typing.Any] = {}

    def app(environ, start_response):
        seen_environ.update(environ)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get(httpx.URL("http://www.example.org/").copy_with(path=path))
    assert response.status_code == 200
    assert seen_environ["PATH_INFO"] == expected_path_info
    assert seen_environ["PATH_INFO"].encode("latin-1").decode("utf-8") == unquote(path)


@pytest.mark.parametrize(
    "script_name, expected_script_name",
    [
        pytest.param("/submount", "/submount", id="ascii"),
        pytest.param("/café", "/caf\xc3\xa9", id="unicode"),
        pytest.param("/caf%C3%A9", "/caf\xc3\xa9", id="percent-encoded"),
    ],
)
def test_wsgi_script_name_is_native_string(
    script_name: str, expected_script_name: str
) -> None:
    seen_environ: dict[str, typing.Any] = {}

    def app(environ, start_response):
        seen_environ.update(environ)
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    transport = httpx.WSGITransport(app=app, script_name=script_name)
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert seen_environ["SCRIPT_NAME"] == expected_script_name


def test_wsgi_write_callable():
    """
    Data passed to the `write()` callable returned by `start_response` is sent
    ahead of the data yielded by the response iterable.
    """

    def app(environ, start_response):
        write = start_response("200 OK", [("Content-Type", "text/plain")])
        write(b"Hello, ")
        return [b"World!"]

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == "Hello, World!"


def test_wsgi_write_callable_from_generator():
    def app(environ, start_response):
        write = start_response("200 OK", [("Content-Type", "text/plain")])
        write(b"1")
        yield b"2"
        write(b"3")
        yield b"4"
        write(b"5")

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == "12345"


def test_wsgi_write_callable_only():
    def app(environ, start_response):
        write = start_response("200 OK", [("Content-Type", "text/plain")])
        write(b"written")
        return []

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get("http://www.example.org/")
    assert response.status_code == 200
    assert response.text == "written"


def test_wsgi_exc_closes_result_iterable():
    """
    When the app exception is re-raised the response iterable's `close()`
    must still be called, as required by PEP 3333.
    """
    closed = False

    class Result:
        def __iter__(self):
            return iter([b"Nope!"])

        def close(self):
            nonlocal closed
            closed = True

    def app(environ, start_response):
        try:
            raise ValueError()
        except ValueError:
            start_response("500 Server Error", [], sys.exc_info())
        return Result()

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    with pytest.raises(ValueError):
        client.get("http://www.example.org/")
    assert closed


def test_wsgi_latin1_headers():
    """
    PEP 3333 header values are latin-1, not ASCII, in both directions.
    """
    seen_environ: dict[str, typing.Any] = {}

    def app(environ, start_response):
        seen_environ.update(environ)
        start_response("200 OK", [("Content-Type", "text/plain"), ("X-Name", "café")])
        return [b"ok"]

    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport)
    response = client.get(
        "http://www.example.org/", headers={b"X-Name": "café".encode("latin-1")}
    )
    assert response.status_code == 200
    assert seen_environ["HTTP_X_NAME"] == "café"
    assert response.headers["X-Name"] == "café"
