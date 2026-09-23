import io
import json
import logging
import os
import random
import subprocess
import sys
import typing

import pytest

import httpx
from httpx._utils import (
    URLPattern,
    get_environment_proxies,
    peek_filelike_length,
    primitive_value_to_str,
    unquote,
)


def httpx_records(caplog: pytest.LogCaptureFixture) -> list:  # type: ignore[type-arg]
    """
    Only the records logged by httpx itself. The test server (uvicorn) also
    logs access records, which show up in `caplog` on some platforms.
    """
    return [record for record in caplog.record_tuples if record[0] == "httpx"]


@pytest.mark.parametrize(
    "encoding",
    (
        "utf-32",
        "utf-8-sig",
        "utf-16",
        "utf-8",
        "utf-16-be",
        "utf-16-le",
        "utf-32-be",
        "utf-32-le",
    ),
)
def test_encoded(encoding):
    content = '{"abc": 123}'.encode(encoding)
    response = httpx.Response(200, content=content)
    assert response.json() == {"abc": 123}


def test_bad_utf_like_encoding():
    content = b"\x00\x00\x00\x00"
    response = httpx.Response(200, content=content)
    with pytest.raises(json.decoder.JSONDecodeError):
        response.json()


@pytest.mark.parametrize(
    ("encoding", "expected"),
    (
        ("utf-16-be", "utf-16"),
        ("utf-16-le", "utf-16"),
        ("utf-32-be", "utf-32"),
        ("utf-32-le", "utf-32"),
    ),
)
def test_guess_by_bom(encoding, expected):
    content = '\ufeff{"abc": 123}'.encode(encoding)
    response = httpx.Response(200, content=content)
    assert response.json() == {"abc": 123}


def test_logging_request(server, caplog):
    caplog.set_level(logging.INFO)
    with httpx.Client() as client:
        response = client.get(server.url)
        assert response.status_code == 200

    assert httpx_records(caplog) == [
        (
            "httpx",
            logging.INFO,
            'HTTP Request: GET http://127.0.0.1:8000/ "HTTP/1.1 200 OK"',
        )
    ]


def test_logging_redirect_chain(server, caplog):
    caplog.set_level(logging.INFO)
    with httpx.Client(follow_redirects=True) as client:
        response = client.get(server.url.copy_with(path="/redirect_301"))
        assert response.status_code == 200

    assert httpx_records(caplog) == [
        (
            "httpx",
            logging.INFO,
            "HTTP Request: GET http://127.0.0.1:8000/redirect_301"
            ' "HTTP/1.1 301 Moved Permanently"',
        ),
        (
            "httpx",
            logging.INFO,
            'HTTP Request: GET http://127.0.0.1:8000/ "HTTP/1.1 200 OK"',
        ),
    ]


@pytest.mark.parametrize(
    ["environment", "proxies"],
    [
        ({}, {}),
        ({"HTTP_PROXY": "http://127.0.0.1"}, {"http://": "http://127.0.0.1"}),
        (
            {"https_proxy": "http://127.0.0.1", "HTTP_PROXY": "https://127.0.0.1"},
            {"https://": "http://127.0.0.1", "http://": "https://127.0.0.1"},
        ),
        ({"all_proxy": "http://127.0.0.1"}, {"all://": "http://127.0.0.1"}),
        ({"TRAVIS_APT_PROXY": "http://127.0.0.1"}, {}),
        ({"no_proxy": "127.0.0.1"}, {"all://127.0.0.1": None}),
        ({"no_proxy": "192.168.0.0/16"}, {"all://192.168.0.0/16": None}),
        ({"no_proxy": "::1"}, {"all://[::1]": None}),
        ({"no_proxy": "[::1]"}, {"all://[::1]": None}),
        ({"no_proxy": "[::1]:8080"}, {"all://[::1]:8080": None}),
        ({"no_proxy": "fd00::/8"}, {"all://[fd00::]/8": None}),
        ({"no_proxy": "10.0.0.0/8"}, {"all://10.0.0.0/8": None}),
        ({"no_proxy": "localhost"}, {"all://localhost": None}),
        ({"no_proxy": "github.com"}, {"all://*github.com": None}),
        ({"no_proxy": ".github.com"}, {"all://*.github.com": None}),
        ({"no_proxy": "*.github.com"}, {"all://*.github.com": None}),
        ({"no_proxy": "*github.com"}, {"all://*github.com": None}),
        ({"no_proxy": "**"}, {}),
        ({"no_proxy": "http://github.com"}, {"http://github.com": None}),
        # NO_PROXY=* disables proxying entirely.
        ({"HTTP_PROXY": "http://127.0.0.1", "no_proxy": "*"}, {}),
        ({"HTTP_PROXY": "http://127.0.0.1", "no_proxy": "github.com,*"}, {}),
    ],
)
def test_get_environment_proxies(environment, proxies):
    os.environ.update(environment)

    assert get_environment_proxies() == proxies


@pytest.mark.parametrize(
    "no_proxy",
    ["[::1]", "[::1]:8080", "fd00::/8", "10.0.0.0/8", "192.168.0.0/16", "*.github.com"],
)
def test_client_accepts_no_proxy_forms(no_proxy):
    """
    Bracketed IPv6, IPv6 CIDR and leading-wildcard NO_PROXY entries used to
    make client construction fail with `InvalidURL`.
    """
    os.environ["HTTP_PROXY"] = "http://127.0.0.1"
    os.environ["NO_PROXY"] = no_proxy

    with httpx.Client() as client:
        assert client._mounts


@pytest.mark.parametrize(
    ["no_proxy", "url", "bypassed"],
    [
        ("10.0.0.0/8", "http://10.1.2.3/", True),
        ("10.0.0.0/8", "http://11.1.2.3/", False),
        ("192.168.0.0/16", "http://192.168.10.20:8000/", True),
        ("192.168.0.0/16", "http://192.169.10.20/", False),
        ("fd00::/8", "http://[fd12::1]/", True),
        ("fd00::/8", "http://[fe80::1]/", False),
        ("[::1]", "http://[::1]/", True),
        ("[::1]:8080", "http://[::1]:8080/", True),
        ("[::1]:8080", "http://[::1]:9090/", False),
        ("*.github.com", "http://api.github.com/", True),
        ("*.github.com", "http://github.com/", False),
    ],
)
def test_no_proxy_bypasses_proxy(no_proxy, url, bypassed):
    os.environ["HTTP_PROXY"] = "http://127.0.0.1"
    os.environ["NO_PROXY"] = no_proxy

    with httpx.Client() as client:
        transport = client._transport_for_url(httpx.URL(url))
        assert (transport is client._transport) is bypassed


@pytest.mark.parametrize(
    ["pattern", "url", "expected"],
    [
        ("http://example.com", "http://example.com", True),
        ("http://example.com", "https://example.com", False),
        ("http://example.com", "http://other.com", False),
        ("http://example.com:123", "http://example.com:123", True),
        ("http://example.com:123", "http://example.com:456", False),
        ("http://example.com:123", "http://example.com", False),
        ("all://example.com", "http://example.com", True),
        ("all://example.com", "https://example.com", True),
        ("http://", "http://example.com", True),
        ("http://", "https://example.com", False),
        ("all://", "https://example.com:123", True),
        ("", "https://example.com:123", True),
        ("all://*example.com", "http://example.com", True),
        ("all://*example.com", "http://www.example.com", True),
        ("all://*example.com", "http://wwwexample.com", False),
        ("all://*.example.com", "http://www.example.com", True),
        ("all://*.example.com", "http://example.com", False),
    ],
)
def test_url_matches(pattern, url, expected):
    pattern = URLPattern(pattern)
    assert pattern.matches(httpx.URL(url)) == expected


def test_url_pattern_requires_url_form():
    with pytest.raises(ValueError, match="Proxy keys should use proper URL forms"):
        URLPattern("http")


@pytest.mark.parametrize(
    ["value", "expected"],
    [(True, "true"), (False, "false"), (None, ""), (1, "1"), ("a", "a")],
)
def test_primitive_value_to_str(value, expected):
    assert primitive_value_to_str(value) == expected


@pytest.mark.parametrize(
    ["pattern", "url", "expected"],
    [
        ("all://10.0.0.0/8", "http://10.255.0.1", True),
        ("all://10.0.0.0/8", "http://11.0.0.1", False),
        ("all://10.1.2.3/8", "http://10.255.0.1", True),  # non-strict network
        ("all://10.0.0.0/8", "http://example.com", False),
        ("all://10.0.0.0/8", "http://[::ffff:a00:1]", False),  # IPv6 vs IPv4 network
        ("http://10.0.0.0/8", "https://10.0.0.1", False),
        ("all://[fd00::]/8", "http://[fd12::1]", True),
        ("all://[fd00::]/8", "http://[fe80::1]", False),
        ("all://[fd00::]/8", "http://10.0.0.1", False),
        # A full-length prefix is an exact address match, not a network.
        ("all://10.0.0.1/32", "http://10.0.0.1", True),
        ("all://10.0.0.1/32", "http://10.0.0.2", False),
        # A path that is not a prefix length is not a network.
        ("all://example.com/8", "http://example.com", True),
        ("all://example.com/8", "http://other.com", False),
    ],
)
def test_url_matches_cidr(pattern, url, expected):
    pattern = URLPattern(pattern)
    assert pattern.matches(httpx.URL(url)) == expected


def test_url_pattern_network_attribute():
    assert URLPattern("all://10.0.0.0/8").network is not None
    assert URLPattern("all://10.0.0.1/32").network is None
    assert URLPattern("all://example.com").network is None
    assert URLPattern("all://").network is None


def test_peek_filelike_length_bytesio():
    stream = io.BytesIO(b"0123456789")
    assert peek_filelike_length(stream) == 10
    assert peek_filelike_length(stream, from_current_position=True) == 10

    stream.read(5)
    assert peek_filelike_length(stream) == 10
    assert peek_filelike_length(stream, from_current_position=True) == 5
    # Peeking must not move the stream.
    assert stream.tell() == 5

    stream.read()
    assert peek_filelike_length(stream, from_current_position=True) == 0


def test_peek_filelike_length_real_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"0123456789")

    with path.open("rb") as stream:
        assert peek_filelike_length(stream) == 10
        stream.read(4)
        assert peek_filelike_length(stream) == 10
        assert peek_filelike_length(stream, from_current_position=True) == 6
        assert stream.tell() == 4


def test_peek_filelike_length_non_regular_file():
    """
    `st_size` is meaningless for pipes, sockets and devices, so the length
    must be reported as unknown rather than as zero.
    """
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"0123456789")
        with os.fdopen(read_fd, "rb", closefd=False) as stream:
            assert peek_filelike_length(stream) is None
    finally:
        os.close(write_fd)
        os.close(read_fd)


def test_peek_filelike_length_broken_tell(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"0123456789")

    class NoTell:
        def __init__(self, file: typing.BinaryIO) -> None:
            self._file = file

        def fileno(self) -> int:
            return self._file.fileno()

        def tell(self) -> int:
            raise OSError("tell() not supported")

    with path.open("rb") as file:
        stream = NoTell(file)
        assert peek_filelike_length(stream) == 10
        assert peek_filelike_length(stream, from_current_position=True) is None


def test_peek_filelike_length_unknown():
    assert peek_filelike_length(object()) is None
    assert peek_filelike_length(iter([b"abc"])) is None


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ('"quoted"', "quoted"),
        ("plain", "plain"),
        ("", ""),
        ('"', '"'),
        ('""', ""),
    ],
)
def test_unquote(value, expected):
    assert unquote(value) == expected


def test_main_is_imported_lazily():
    """
    `import httpx` should not import the command line client (and with it
    `click`, `rich` and `pygments`) until `httpx.main` is actually used.
    """
    script = (
        "import sys, httpx; "
        "assert 'httpx._main' not in sys.modules, 'httpx._main imported eagerly'; "
        "assert 'click' not in sys.modules, 'click imported eagerly'; "
        "assert callable(httpx.main); "
        "assert httpx.main.name == 'main'; "
        "assert 'httpx._main' in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def test_main_proxies_to_click_command():
    from httpx._main import main as click_main

    assert httpx.main.name == click_main.name
    assert httpx.main.main == click_main.main
    # Dunder lookups are answered locally and never trigger the import.
    assert not hasattr(httpx.main, "__wrapped__")


def test_main_is_callable(capsys):
    """
    `httpx.main` is the `httpx` console script entry point, so calling it
    must run the click command.
    """
    with pytest.raises(SystemExit) as exc_info:
        httpx.main(["--help"])

    assert exc_info.value.code == 0
    assert "A next generation HTTP client." in capsys.readouterr().out


def test_pattern_priority():
    matchers = [
        URLPattern("all://"),
        URLPattern("http://"),
        URLPattern("http://example.com"),
        URLPattern("http://example.com:123"),
    ]
    random.shuffle(matchers)
    assert sorted(matchers) == [
        URLPattern("http://example.com:123"),
        URLPattern("http://example.com"),
        URLPattern("http://"),
        URLPattern("all://"),
    ]
