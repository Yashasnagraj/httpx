import ssl
import typing
from pathlib import Path

import certifi
import pytest

import httpx


def test_load_ssl_config():
    context = httpx.create_ssl_context()
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


def test_load_ssl_config_verify_non_existing_file():
    with pytest.raises(IOError):
        context = httpx.create_ssl_context()
        context.load_verify_locations(cafile="/path/to/nowhere")


def test_load_ssl_with_keylog(monkeypatch: typing.Any) -> None:
    monkeypatch.setenv("SSLKEYLOGFILE", "test")
    context = httpx.create_ssl_context()
    assert context.keylog_filename == "test"


def test_load_ssl_config_verify_existing_file():
    context = httpx.create_ssl_context()
    context.load_verify_locations(capath=certifi.where())
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


def test_load_ssl_config_verify_directory():
    context = httpx.create_ssl_context()
    context.load_verify_locations(capath=Path(certifi.where()).parent)
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


def test_load_ssl_config_cert_and_key(cert_pem_file, cert_private_key_file):
    context = httpx.create_ssl_context()
    context.load_cert_chain(cert_pem_file, cert_private_key_file)
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


@pytest.mark.parametrize("password", [b"password", "password"])
def test_load_ssl_config_cert_and_encrypted_key(
    cert_pem_file, cert_encrypted_private_key_file, password
):
    context = httpx.create_ssl_context()
    context.load_cert_chain(cert_pem_file, cert_encrypted_private_key_file, password)
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


def test_load_ssl_config_cert_and_key_invalid_password(
    cert_pem_file, cert_encrypted_private_key_file
):
    with pytest.raises(ssl.SSLError):
        context = httpx.create_ssl_context()
        context.load_cert_chain(
            cert_pem_file, cert_encrypted_private_key_file, "password1"
        )


def test_load_ssl_config_cert_without_key_raises(cert_pem_file):
    with pytest.raises(ssl.SSLError):
        context = httpx.create_ssl_context()
        context.load_cert_chain(cert_pem_file)


def test_load_ssl_config_verify_str_applies_cert(
    monkeypatch, cert_pem_file, cert_private_key_file
):
    """
    The deprecated `verify=<str>` form used to return early and silently
    ignore an accompanying `cert=...` argument.
    """
    calls = []

    def load_cert_chain(self, *args):
        calls.append(args)

    monkeypatch.setattr(ssl.SSLContext, "load_cert_chain", load_cert_chain)

    with pytest.warns(DeprecationWarning):
        context = httpx.create_ssl_context(
            verify=cert_pem_file, cert=(cert_pem_file, cert_private_key_file)
        )

    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert calls == [(cert_pem_file, cert_private_key_file)]

    calls.clear()
    with pytest.warns(DeprecationWarning):
        httpx.create_ssl_context(verify=cert_pem_file, cert=cert_pem_file)
    assert calls == [(cert_pem_file,)]


def test_load_ssl_config_verify_str_directory(cert_pem_file, cert_private_key_file):
    with pytest.warns(DeprecationWarning):
        context = httpx.create_ssl_context(
            verify=str(Path(certifi.where()).parent),
            cert=(cert_pem_file, cert_private_key_file),
        )
    assert context.verify_mode == ssl.VerifyMode.CERT_REQUIRED
    assert context.check_hostname is True


def test_load_ssl_config_no_verify():
    context = httpx.create_ssl_context(verify=False)
    assert context.verify_mode == ssl.VerifyMode.CERT_NONE
    assert context.check_hostname is False


def test_SSLContext_with_get_request(server, cert_pem_file):
    context = httpx.create_ssl_context()
    context.load_verify_locations(cert_pem_file)
    response = httpx.get(server.url, verify=context)
    assert response.status_code == 200


def test_limits_repr():
    limits = httpx.Limits(max_connections=100)
    expected = (
        "Limits(max_connections=100, max_keepalive_connections=None,"
        " keepalive_expiry=5.0)"
    )
    assert repr(limits) == expected


def test_limits_eq():
    limits = httpx.Limits(max_connections=100)
    assert limits == httpx.Limits(max_connections=100)


def test_timeout_eq():
    timeout = httpx.Timeout(timeout=5.0)
    assert timeout == httpx.Timeout(timeout=5.0)


def test_timeout_all_parameters_set():
    timeout = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)
    assert timeout == httpx.Timeout(timeout=5.0)


def test_timeout_from_nothing():
    timeout = httpx.Timeout(None)
    assert timeout.connect is None
    assert timeout.read is None
    assert timeout.write is None
    assert timeout.pool is None


def test_timeout_from_none():
    timeout = httpx.Timeout(timeout=None)
    assert timeout == httpx.Timeout(None)


def test_timeout_from_one_none_value():
    timeout = httpx.Timeout(None, read=None)
    assert timeout == httpx.Timeout(None)


def test_timeout_from_one_value():
    timeout = httpx.Timeout(None, read=5.0)
    assert timeout == httpx.Timeout(timeout=(None, 5.0, None, None))


def test_timeout_from_one_value_and_default():
    timeout = httpx.Timeout(5.0, pool=60.0)
    assert timeout == httpx.Timeout(timeout=(5.0, 5.0, 5.0, 60.0))


def test_timeout_missing_default():
    with pytest.raises(ValueError):
        httpx.Timeout(pool=60.0)


def test_timeout_from_tuple():
    timeout = httpx.Timeout(timeout=(5.0, 5.0, 5.0, 5.0))
    assert timeout == httpx.Timeout(timeout=5.0)


def test_timeout_from_config_instance():
    timeout = httpx.Timeout(timeout=5.0)
    assert httpx.Timeout(timeout) == httpx.Timeout(timeout=5.0)


@pytest.mark.parametrize(
    "overrides",
    [{"connect": 1.0}, {"read": None}, {"write": 1.0}, {"pool": 1.0}],
)
def test_timeout_from_config_instance_with_overrides_raises(overrides):
    """
    Combining a Timeout instance with per-operation overrides is ambiguous,
    and must raise a clear ValueError rather than silently dropping the
    overrides (or a bare AssertionError).
    """
    timeout = httpx.Timeout(timeout=5.0)
    with pytest.raises(ValueError, match="cannot combine"):
        httpx.Timeout(timeout, **overrides)


@pytest.mark.parametrize("value", [(), (5.0,), (1.0, 2.0, 3.0, 4.0, 5.0)])
def test_timeout_from_invalid_tuple_raises(value):
    with pytest.raises(ValueError, match="between 2 and 4 items"):
        httpx.Timeout(value)


@pytest.mark.parametrize(
    ["value", "expected"],
    [
        ((1.0, 2.0), (1.0, 2.0, None, None)),
        ((1.0, 2.0, 3.0), (1.0, 2.0, 3.0, None)),
        ((1.0, 2.0, 3.0, 4.0), (1.0, 2.0, 3.0, 4.0)),
    ],
)
def test_timeout_from_valid_tuples(value, expected):
    timeout = httpx.Timeout(value)
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == expected


def test_timeout_repr():
    timeout = httpx.Timeout(timeout=5.0)
    assert repr(timeout) == "Timeout(timeout=5.0)"

    timeout = httpx.Timeout(None, read=5.0)
    assert repr(timeout) == "Timeout(connect=None, read=5.0, write=None, pool=None)"


def test_proxy_from_url():
    proxy = httpx.Proxy("https://example.com")

    assert str(proxy.url) == "https://example.com"
    assert proxy.auth is None
    assert proxy.headers == {}
    assert repr(proxy) == "Proxy('https://example.com')"


def test_proxy_with_auth_from_url():
    proxy = httpx.Proxy("https://username:password@example.com")

    assert str(proxy.url) == "https://example.com"
    assert proxy.auth == ("username", "password")
    assert proxy.headers == {}
    assert repr(proxy) == "Proxy('https://example.com', auth=('username', '********'))"


def test_proxy_explicit_auth_overrides_url_auth():
    """
    An explicit `auth=` argument takes precedence over credentials in the URL.
    """
    proxy = httpx.Proxy(
        "https://username:password@example.com", auth=("other", "secret")
    )

    assert str(proxy.url) == "https://example.com"
    assert proxy.auth == ("other", "secret")
    assert proxy.raw_auth == (b"other", b"secret")
    assert repr(proxy) == "Proxy('https://example.com', auth=('other', '********'))"


def test_invalid_proxy_scheme():
    with pytest.raises(ValueError):
        httpx.Proxy("invalid://example.com")
