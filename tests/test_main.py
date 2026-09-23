import os
import sys
import typing

import httpcore
import pytest
from click.testing import CliRunner

import httpx
import httpx._main


def splitlines(output: str) -> typing.Iterable[str]:
    return [line.strip() for line in output.splitlines()]


def remove_date_header(lines: typing.Iterable[str]) -> typing.Iterable[str]:
    return [line for line in lines if not line.startswith("date:")]


def test_help():
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["--help"])
    assert result.exit_code == 0
    assert "A next generation HTTP client." in result.output


def test_get(server):
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        "Hello, world!",
    ]


def test_json(server):
    url = str(server.url.copy_with(path="/json"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: application/json",
        "Transfer-Encoding: chunked",
        "",
        "{",
        '"Hello": "world!"',
        "}",
    ]


def test_binary(server):
    url = str(server.url.copy_with(path="/echo_binary"))
    runner = CliRunner()
    content = "Hello, world!"
    result = runner.invoke(httpx.main, [url, "-c", content])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: application/octet-stream",
        "Transfer-Encoding: chunked",
        "",
        f"<{len(content)} bytes of binary data>",
    ]


def test_redirects(server):
    url = str(server.url.copy_with(path="/redirect_301"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url])
    assert result.exit_code == 1
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 301 Moved Permanently",
        "server: uvicorn",
        "location: /",
        "Transfer-Encoding: chunked",
        "",
    ]


def test_follow_redirects(server):
    url = str(server.url.copy_with(path="/redirect_301"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "--follow-redirects"])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 301 Moved Permanently",
        "server: uvicorn",
        "location: /",
        "Transfer-Encoding: chunked",
        "",
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        "Hello, world!",
    ]


def test_post(server):
    url = str(server.url.copy_with(path="/echo_body"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "-m", "POST", "-j", '{"hello": "world"}'])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        '{"hello":"world"}',
    ]


def test_verbose(server):
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "-v"])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "* Connecting to '127.0.0.1'",
        "* Connected to '127.0.0.1' on port 8000",
        "GET / HTTP/1.1",
        f"Host: {server.url.netloc.decode('ascii')}",
        "Accept: */*",
        "Accept-Encoding: gzip, deflate, br, zstd",
        "Connection: keep-alive",
        f"User-Agent: python-httpx/{httpx.__version__}",
        "",
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        "Hello, world!",
    ]


def test_auth(server):
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "-v", "--auth", "username", "password"])
    print(result.output)
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "* Connecting to '127.0.0.1'",
        "* Connected to '127.0.0.1' on port 8000",
        "GET / HTTP/1.1",
        f"Host: {server.url.netloc.decode('ascii')}",
        "Accept: */*",
        "Accept-Encoding: gzip, deflate, br, zstd",
        "Connection: keep-alive",
        f"User-Agent: python-httpx/{httpx.__version__}",
        "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ=",
        "",
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        "Hello, world!",
    ]


def test_download(server):
    url = str(server.url)
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(httpx.main, [url, "--download", "index.txt"])
        assert os.path.exists("index.txt")
        with open("index.txt", "r") as input_file:
            assert input_file.read() == "Hello, world!"


def test_errors():
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["invalid://example.org"])
    assert result.exit_code == 1
    assert splitlines(result.output) == [
        "UnsupportedProtocol: Request URL has an unsupported protocol 'invalid://'.",
    ]


# Regression tests.


@pytest.fixture
def mock_client(monkeypatch):
    """
    Route the CLI's requests to a `MockTransport` handler.
    """

    def install(handler):
        def make_client(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx._main, "Client", make_client)

    return install


def test_format_response_headers_latin1():
    text = httpx._main.format_response_headers(
        b"HTTP/1.1", 200, b"Caf\xe9", [(b"x-name", b"caf\xe9")]
    )
    assert text == "HTTP/1.1 200 Café\nx-name: café"


def test_format_request_headers_latin1():
    request = httpcore.Request(
        "GET", "http://example.org/", headers=[(b"x-name", b"caf\xe9")]
    )
    text = httpx._main.format_request_headers(request)
    assert text == "GET / HTTP/1.1\nx-name: café"


def test_header_value_not_encodable(server):
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "-h", "X-Name", "✓"])
    assert result.exit_code == 1
    assert list(splitlines(result.output))[0].startswith("UnicodeEncodeError: ")


def test_text_csv_body(mock_client):
    mock_client(
        lambda request: httpx.Response(
            200, headers={"Content-Type": "text/csv"}, content=b"a,b\n1,2"
        )
    )
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["a,b", "1,2"]


def test_json_suffix_body(mock_client):
    mock_client(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/problem+json"},
            content='{"title": "Nope", "detail": "café"}'.encode("utf-8"),
        )
    )
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == [
        "{",
        '"title": "Nope",',
        '"detail": "café"',
        "}",
    ]


def test_xml_suffix_body(mock_client):
    mock_client(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/vnd.example+xml"},
            content=b"<feed/>",
        )
    )
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["<feed/>"]


def test_invalid_json_body(mock_client):
    mock_client(
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/json"}, content=b"not json"
        )
    )
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["not json"]


def test_unknown_mime_type_body(mock_client):
    mock_client(
        lambda request: httpx.Response(
            200, headers={"Content-Type": "application/x-unknown"}, content=b"???"
        )
    )
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["<3 bytes of binary data>"]


def test_missing_content_type_text_body(mock_client):
    mock_client(lambda request: httpx.Response(200, content="Hello, ✓".encode()))
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["Hello, ✓"]


def test_missing_content_type_binary_body(mock_client):
    mock_client(lambda request: httpx.Response(200, content=b"\xff\xfe\x00"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, ["http://example.org/"])
    assert result.exit_code == 0
    assert splitlines(result.output) == ["<3 bytes of binary data>"]


def test_http2_without_h2(server, monkeypatch):
    monkeypatch.setitem(sys.modules, "h2", None)
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "--http2"])
    assert result.exit_code == 1
    assert list(splitlines(result.output))[0].startswith("ImportError: ")
    assert "httpx[http2]" in result.output


def test_socks_proxy_without_socksio(server, monkeypatch):
    monkeypatch.setitem(sys.modules, "socksio", None)
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "--proxy", "socks5://localhost:1080"])
    assert result.exit_code == 1
    assert list(splitlines(result.output))[0].startswith("ImportError: ")
    assert "httpx[socks]" in result.output


def test_invalid_proxy_scheme(server):
    url = str(server.url)
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "--proxy", "ftp://localhost"])
    assert result.exit_code == 1
    assert splitlines(result.output) == [
        "ValueError: Unknown scheme for proxy URL URL('ftp://localhost')"
    ]


def test_multiple_body_options(server):
    url = str(server.url.copy_with(path="/echo_body"))
    runner = CliRunner()
    result = runner.invoke(
        httpx.main, [url, "-c", "content", "-j", '{"hello": "world"}']
    )
    assert result.exit_code == 2
    assert "Only one of --content, --data, --files or --json" in result.output
    assert "--content and --json" in result.output


def test_repeated_data_values(server):
    url = str(server.url.copy_with(path="/echo_body"))
    runner = CliRunner()
    result = runner.invoke(httpx.main, [url, "-d", "a", "1", "-d", "a", "2"])
    assert result.exit_code == 0
    assert remove_date_header(splitlines(result.output)) == [
        "HTTP/1.1 200 OK",
        "server: uvicorn",
        "content-type: text/plain",
        "Transfer-Encoding: chunked",
        "",
        "a=1&a=2",
    ]
