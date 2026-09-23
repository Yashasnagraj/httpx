"""
Unit tests for auth classes.

Integration tests also exist in tests/client/test_auth.py
"""

import hashlib
from urllib.request import parse_keqv_list

import pytest

import httpx


def test_basic_auth():
    auth = httpx.BasicAuth(username="user", password="pass")
    request = httpx.Request("GET", "https://www.example.com")

    # The initial request should include a basic auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert request.headers["Authorization"].startswith("Basic")

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_with_200():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = httpx.Request("GET", "https://www.example.com")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 200 response is returned, then no other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_with_401():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = httpx.Request("GET", "https://www.example.com")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 401 response is returned, then a digest auth request is made.
    headers = {
        "WWW-Authenticate": 'Digest realm="...", qop="auth", nonce="...", opaque="..."'
    }
    response = httpx.Response(
        content=b"Auth required", status_code=401, headers=headers, request=request
    )
    request = flow.send(response)
    assert request.headers["Authorization"].startswith("Digest")

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_with_401_nonce_counting():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = httpx.Request("GET", "https://www.example.com")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 401 response is returned, then a digest auth request is made.
    headers = {
        "WWW-Authenticate": 'Digest realm="...", qop="auth", nonce="...", opaque="..."'
    }
    response = httpx.Response(
        content=b"Auth required", status_code=401, headers=headers, request=request
    )
    first_request = flow.send(response)
    assert first_request.headers["Authorization"].startswith("Digest")

    # Each subsequent request contains the digest header by default...
    request = httpx.Request("GET", "https://www.example.com")
    flow = auth.sync_auth_flow(request)
    second_request = next(flow)
    assert second_request.headers["Authorization"].startswith("Digest")

    # ... and the client nonce count (nc) is increased
    first_nc = parse_keqv_list(first_request.headers["Authorization"].split(", "))["nc"]
    second_nc = parse_keqv_list(second_request.headers["Authorization"].split(", "))[
        "nc"
    ]
    assert int(first_nc, 16) + 1 == int(second_nc, 16)

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def set_cookies(request: httpx.Request) -> httpx.Response:
    headers = {
        "Set-Cookie": "session=.session_value...",
        "WWW-Authenticate": 'Digest realm="...", qop="auth", nonce="...", opaque="..."',
    }
    if request.url.path == "/auth":
        return httpx.Response(
            content=b"Auth required", status_code=401, headers=headers
        )
    else:
        raise NotImplementedError()  # pragma: no cover


def test_digest_auth_setting_cookie_in_request():
    url = "https://www.example.com/auth"
    client = httpx.Client(transport=httpx.MockTransport(set_cookies))
    request = client.build_request("GET", url)

    auth = httpx.DigestAuth(username="user", password="pass")
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    response = client.get(url)
    assert len(response.cookies) > 0
    assert response.cookies["session"] == ".session_value..."

    request = flow.send(response)
    assert request.headers["Authorization"].startswith("Digest")
    assert request.headers["Cookie"] == "session=.session_value..."

    # No other requests are made.
    response = httpx.Response(
        content=b"Hello, world!", status_code=200, request=request
    )
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_rfc_2069():
    # Example from https://datatracker.ietf.org/doc/html/rfc2069#section-2.4
    # with corrected response from https://www.rfc-editor.org/errata/eid749

    auth = httpx.DigestAuth(username="Mufasa", password="CircleOfLife")
    request = httpx.Request("GET", "https://www.example.com/dir/index.html")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 401 response is returned, then a digest auth request is made.
    headers = {
        "WWW-Authenticate": (
            'Digest realm="testrealm@host.com", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
            'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
    }
    response = httpx.Response(
        content=b"Auth required", status_code=401, headers=headers, request=request
    )
    request = flow.send(response)
    assert request.headers["Authorization"].startswith("Digest")
    assert 'username="Mufasa"' in request.headers["Authorization"]
    assert 'realm="testrealm@host.com"' in request.headers["Authorization"]
    assert (
        'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093"' in request.headers["Authorization"]
    )
    assert 'uri="/dir/index.html"' in request.headers["Authorization"]
    assert (
        'opaque="5ccc069c403ebaf9f0171e9517f40e41"' in request.headers["Authorization"]
    )
    assert (
        'response="1949323746fe6a43ef61f9606e7febea"'
        in request.headers["Authorization"]
    )

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_rfc_7616_md5(monkeypatch):
    # Example from https://datatracker.ietf.org/doc/html/rfc7616#section-3.9.1

    def mock_get_client_nonce(nonce_count: int, nonce: bytes) -> bytes:
        return "f2/wE4q74E6zIJEtWaHKaf5wv/H5QzzpXusqGemxURZJ".encode()

    auth = httpx.DigestAuth(username="Mufasa", password="Circle of Life")
    monkeypatch.setattr(auth, "_get_client_nonce", mock_get_client_nonce)

    request = httpx.Request("GET", "https://www.example.com/dir/index.html")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 401 response is returned, then a digest auth request is made.
    headers = {
        "WWW-Authenticate": (
            'Digest realm="http-auth@example.org", '
            'qop="auth, auth-int", '
            "algorithm=MD5, "
            'nonce="7ypf/xlj9XXwfDPEoM4URrv/xwf94BcCAzFZH4GiTo0v", '
            'opaque="FQhe/qaU925kfnzjCev0ciny7QMkPqMAFRtzCUYo5tdS"'
        )
    }
    response = httpx.Response(
        content=b"Auth required", status_code=401, headers=headers, request=request
    )
    request = flow.send(response)
    assert request.headers["Authorization"].startswith("Digest")
    assert 'username="Mufasa"' in request.headers["Authorization"]
    assert 'realm="http-auth@example.org"' in request.headers["Authorization"]
    assert 'uri="/dir/index.html"' in request.headers["Authorization"]
    assert "algorithm=MD5" in request.headers["Authorization"]
    assert (
        'nonce="7ypf/xlj9XXwfDPEoM4URrv/xwf94BcCAzFZH4GiTo0v"'
        in request.headers["Authorization"]
    )
    assert "nc=00000001" in request.headers["Authorization"]
    assert (
        'cnonce="f2/wE4q74E6zIJEtWaHKaf5wv/H5QzzpXusqGemxURZJ"'
        in request.headers["Authorization"]
    )
    assert "qop=auth" in request.headers["Authorization"]
    assert (
        'opaque="FQhe/qaU925kfnzjCev0ciny7QMkPqMAFRtzCUYo5tdS"'
        in request.headers["Authorization"]
    )
    assert (
        'response="8ca523f5e9506fed4657c9700eebdbec"'
        in request.headers["Authorization"]
    )

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_rfc_7616_sha_256(monkeypatch):
    # Example from https://datatracker.ietf.org/doc/html/rfc7616#section-3.9.1

    def mock_get_client_nonce(nonce_count: int, nonce: bytes) -> bytes:
        return "f2/wE4q74E6zIJEtWaHKaf5wv/H5QzzpXusqGemxURZJ".encode()

    auth = httpx.DigestAuth(username="Mufasa", password="Circle of Life")
    monkeypatch.setattr(auth, "_get_client_nonce", mock_get_client_nonce)

    request = httpx.Request("GET", "https://www.example.com/dir/index.html")

    # The initial request should not include an auth header.
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    assert "Authorization" not in request.headers

    # If a 401 response is returned, then a digest auth request is made.
    headers = {
        "WWW-Authenticate": (
            'Digest realm="http-auth@example.org", '
            'qop="auth, auth-int", '
            "algorithm=SHA-256, "
            'nonce="7ypf/xlj9XXwfDPEoM4URrv/xwf94BcCAzFZH4GiTo0v", '
            'opaque="FQhe/qaU925kfnzjCev0ciny7QMkPqMAFRtzCUYo5tdS"'
        )
    }
    response = httpx.Response(
        content=b"Auth required", status_code=401, headers=headers, request=request
    )
    request = flow.send(response)
    assert request.headers["Authorization"].startswith("Digest")
    assert 'username="Mufasa"' in request.headers["Authorization"]
    assert 'realm="http-auth@example.org"' in request.headers["Authorization"]
    assert 'uri="/dir/index.html"' in request.headers["Authorization"]
    assert "algorithm=SHA-256" in request.headers["Authorization"]
    assert (
        'nonce="7ypf/xlj9XXwfDPEoM4URrv/xwf94BcCAzFZH4GiTo0v"'
        in request.headers["Authorization"]
    )
    assert "nc=00000001" in request.headers["Authorization"]
    assert (
        'cnonce="f2/wE4q74E6zIJEtWaHKaf5wv/H5QzzpXusqGemxURZJ"'
        in request.headers["Authorization"]
    )
    assert "qop=auth" in request.headers["Authorization"]
    assert (
        'opaque="FQhe/qaU925kfnzjCev0ciny7QMkPqMAFRtzCUYo5tdS"'
        in request.headers["Authorization"]
    )
    assert (
        'response="753927fa0e85d155564e2e272a28d1802ca10daf4496794697cf8db5856cb6c1"'
        in request.headers["Authorization"]
    )

    # No other requests are made.
    response = httpx.Response(content=b"Hello, world!", status_code=200)
    with pytest.raises(StopIteration):
        flow.send(response)


def _send_401(auth: httpx.DigestAuth, url: str, www_authenticate: str) -> httpx.Request:
    """
    Run a single Digest auth flow: an initial unauthenticated request, a 401
    challenge, and return the authenticated request that is sent in reply.
    """
    request = httpx.Request("GET", url)
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    response = httpx.Response(
        status_code=401,
        headers={"WWW-Authenticate": www_authenticate},
        request=request,
    )
    return flow.send(response)


def _authorization_fields(request: httpx.Request) -> dict[str, str]:
    scheme, _, fields = request.headers["Authorization"].partition(" ")
    assert scheme == "Digest"
    return parse_keqv_list([field.strip() for field in fields.split(", ")])


def test_digest_auth_unsupported_algorithm():
    auth = httpx.DigestAuth(username="user", password="pass")
    with pytest.raises(httpx.ProtocolError, match="Unsupported Digest algorithm"):
        _send_401(
            auth,
            "https://www.example.com",
            'Digest realm="r", nonce="n", qop="auth", algorithm=SHA-3-512',
        )


@pytest.mark.parametrize("algorithm", ["SHA-512-256", "SHA-512-256-SESS"])
def test_digest_auth_sha_512_256(algorithm):
    auth = httpx.DigestAuth(username="user", password="pass")
    request = _send_401(
        auth,
        "https://www.example.com",
        f'Digest realm="r", nonce="n", qop="auth", algorithm={algorithm}',
    )
    fields = _authorization_fields(request)
    assert fields["algorithm"] == algorithm
    # SHA-512/256 produces a 256-bit (64 hex character) digest.
    assert len(fields["response"]) == 64


def test_digest_auth_sha_512_256_response_value(monkeypatch):
    """
    The SHA-512-256 response must be computed with the SHA-512/256 primitive
    (RFC 7616, Section 3.9.2), not with plain SHA-512 truncated or similar.
    """
    cnonce = "NTg6RKcb9boFIAS3KrFK9BGeh+iDa/sm6jUMp2wds69v"
    nonce = "5TsQWLVdgBdmrQ0XsxbDODV+57QdFR34I9HAbC/RVvkK"

    def mock_get_client_nonce(nonce_count: int, nonce: bytes) -> bytes:
        return cnonce.encode()

    auth = httpx.DigestAuth(username="user", password="Secret, or not?")
    monkeypatch.setattr(auth, "_get_client_nonce", mock_get_client_nonce)

    request = _send_401(
        auth,
        "https://api.example.org/doe.json",
        'Digest realm="api@example.org", qop="auth", algorithm=SHA-512-256, '
        f'nonce="{nonce}"',
    )
    fields = _authorization_fields(request)
    assert fields["algorithm"] == "SHA-512-256"
    assert fields["nc"] == "00000001"

    def h(data: str) -> str:
        return hashlib.new("sha512_256", data.encode()).hexdigest()

    ha1 = h("user:api@example.org:Secret, or not?")
    ha2 = h("GET:/doe.json")
    expected = h(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")
    assert fields["response"] == expected


@pytest.mark.parametrize(
    "www_authenticate",
    [
        'Digest realm="r", nonce="n", qop="auth", stale',  # bare token without "="
        'Digest realm="r", nonce="n", qop="auth", , foo',
    ],
)
def test_digest_auth_malformed_field_raises_protocol_error(www_authenticate):
    auth = httpx.DigestAuth(username="user", password="pass")
    with pytest.raises(httpx.ProtocolError, match="Malformed Digest"):
        _send_401(auth, "https://www.example.com", www_authenticate)


def test_digest_auth_empty_value():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = _send_401(
        auth,
        "https://www.example.com",
        'Digest realm="r", nonce="n", qop="auth", opaque=',
    )
    fields = _authorization_fields(request)
    assert "opaque" not in fields
    assert fields["realm"] == "r"


def test_digest_auth_case_insensitive_parameter_names():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = _send_401(
        auth,
        "https://www.example.com",
        'Digest Realm="r", NONCE="n", Qop="auth", Algorithm=SHA-256, Opaque="o"',
    )
    fields = _authorization_fields(request)
    assert fields["realm"] == "r"
    assert fields["nonce"] == "n"
    assert fields["opaque"] == "o"
    assert fields["algorithm"] == "SHA-256"
    assert fields["qop"] == "auth"


@pytest.mark.parametrize(
    "www_authenticate",
    [
        'Basic realm="r", Digest realm="d", nonce="n", qop="auth"',
        'Basic realm="r",digest realm="d", nonce="n", qop="auth"',
        'Bearer realm="r", DIGEST realm="d", nonce="n", qop="auth"',
    ],
)
def test_digest_auth_multiple_challenges(www_authenticate):
    """
    A single `WWW-Authenticate` header may carry several challenges. The
    Digest challenge must be found even when it is not the first one.
    """
    auth = httpx.DigestAuth(username="user", password="pass")
    request = _send_401(auth, "https://www.example.com", www_authenticate)
    fields = _authorization_fields(request)
    assert fields["realm"] == "d"
    assert fields["nonce"] == "n"


def test_digest_auth_bare_scheme_is_not_a_challenge():
    auth = httpx.DigestAuth(username="user", password="pass")
    request = httpx.Request("GET", "https://www.example.com")
    flow = auth.sync_auth_flow(request)
    request = next(flow)
    response = httpx.Response(
        status_code=401, headers={"WWW-Authenticate": "Digest"}, request=request
    )
    with pytest.raises(StopIteration):
        flow.send(response)


def test_digest_auth_challenge_is_cached_per_origin():
    """
    A challenge received from one origin must not be sent pre-emptively to a
    different origin, since the realm and nonce are bound to the server that
    issued them.
    """
    auth = httpx.DigestAuth(username="user", password="pass")
    challenge = 'Digest realm="a", nonce="n", qop="auth"'
    _send_401(auth, "https://a.example.com/", challenge)

    # Same origin: the cached challenge is reused pre-emptively.
    request = next(auth.sync_auth_flow(httpx.Request("GET", "https://a.example.com/x")))
    assert _authorization_fields(request)["realm"] == "a"
    assert _authorization_fields(request)["nc"] == "00000002"

    # Different host, scheme, or port: no pre-emptive Authorization header.
    for url in (
        "https://b.example.com/",
        "http://a.example.com/",
        "https://a.example.com:8443/",
    ):
        request = next(auth.sync_auth_flow(httpx.Request("GET", url)))
        assert "Authorization" not in request.headers

    # The other origin gets its own challenge and nonce count.
    request = _send_401(
        auth, "https://b.example.com/", 'Digest realm="b", nonce="m", qop="auth"'
    )
    assert _authorization_fields(request)["realm"] == "b"
    assert _authorization_fields(request)["nc"] == "00000001"

    request = next(auth.sync_auth_flow(httpx.Request("GET", "https://a.example.com/")))
    assert _authorization_fields(request)["realm"] == "a"
    assert _authorization_fields(request)["nc"] == "00000003"


def test_digest_auth_escapes_quoted_values():
    auth = httpx.DigestAuth(username='us"er\\name', password="pass")
    request = _send_401(
        auth,
        "https://www.example.com",
        'Digest realm="re\\"alm", nonce="n", qop="auth", opaque="o"',
    )
    header = request.headers["Authorization"]
    assert 'username="us\\"er\\\\name"' in header
    # `parse_http_list` unescapes the challenge's `re\"alm` to `re"alm`, which
    # must then be re-escaped when it is echoed back.
    assert 'realm="re\\"alm"' in header
    # Non-quoted fields are not escaped.
    assert "algorithm=MD5" in header
