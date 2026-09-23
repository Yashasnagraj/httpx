<p align="center">
  <a href="https://www.python-httpx.org/"><img width="350" height="208" src="https://raw.githubusercontent.com/encode/httpx/master/docs/img/butterfly.png" alt='HTTPX'></a>
</p>

<p align="center"><strong>HTTPX</strong> <em>- A next-generation HTTP client for Python.</em></p>

<p align="center">
<a href="https://github.com/encode/httpx/actions">
    <img src="https://github.com/encode/httpx/workflows/Test%20Suite/badge.svg" alt="Test Suite">
</a>
<a href="https://pypi.org/project/httpx/">
    <img src="https://badge.fury.io/py/httpx.svg" alt="Package version">
</a>
</p>

HTTPX is a fully featured HTTP client library for Python 3. It includes **an integrated command line client**, has support for both **HTTP/1.1 and HTTP/2**, and provides both **sync and async APIs**.

---

Install HTTPX using pip:

```shell
$ pip install httpx
```

Now, let's get started:

```pycon
>>> import httpx
>>> r = httpx.get('https://www.example.org/')
>>> r
<Response [200 OK]>
>>> r.status_code
200
>>> r.headers['content-type']
'text/html; charset=UTF-8'
>>> r.text
'<!doctype html>\n<html>\n<head>\n<title>Example Domain</title>...'
```

Or, using the command-line client.

```shell
$ pip install 'httpx[cli]'  # The command line client is an optional dependency.
```

Which now allows us to use HTTPX directly from the command-line...

<p align="center">
  <img width="700" src="docs/img/httpx-help.png" alt='httpx --help'>
</p>

Sending a request...

<p align="center">
  <img width="700" src="docs/img/httpx-request.png" alt='httpx http://httpbin.org/json'>
</p>

## Features

HTTPX builds on the well-established usability of `requests`, and gives you:

* A broadly [requests-compatible API](https://www.python-httpx.org/compatibility/).
* An integrated command-line client.
* HTTP/1.1 [and HTTP/2 support](https://www.python-httpx.org/http2/).
* Standard synchronous interface, but with [async support if you need it](https://www.python-httpx.org/async/).
* Ability to make requests directly to [WSGI applications](https://www.python-httpx.org/advanced/transports/#wsgi-transport) or [ASGI applications](https://www.python-httpx.org/advanced/transports/#asgi-transport).
* Strict timeouts everywhere.
* Fully type annotated.
* 100% test coverage.

Plus all the standard features of `requests`...

* International Domains and URLs
* Keep-Alive & Connection Pooling
* Sessions with Cookie Persistence
* Browser-style SSL Verification
* Basic/Digest Authentication
* Elegant Key/Value Cookies
* Automatic Decompression
* Automatic Content Decoding
* Unicode Response Bodies
* Multipart File Uploads
* HTTP(S) Proxy Support
* Connection Timeouts
* Streaming Downloads
* .netrc Support
* Chunked Requests

## Review findings and fixes (this fork)

This fork was audited end to end (library code, CLI, transports, tests, docs, packaging and CI) against httpx 0.28.1. Every problem below was reproduced with a script before it was fixed, every fix has a regression test, and the suite still enforces 100% coverage.

### Requests and responses

| Problem | Fix |
| --- | --- |
| A `307`/`308` redirect or auth retry re-sent a `BytesIO`/iterator body as **empty** while still declaring the original `Content-Length`, so servers hung waiting for bytes. | `IteratorByteStream` rewinds seekable file-likes to their starting offset and raises `StreamConsumed` for one-shot iterators (`httpx/_content.py`). |
| `content=<partially read file>` sent the file's total size as `Content-Length`, not the remaining bytes. | `peek_filelike_length` subtracts the current position and only trusts `st_size` for regular files, so pipes use chunked encoding (`httpx/_utils.py`). |
| Multi-member gzip bodies were silently truncated after the first member. | `GZipDecoder` restarts on `unused_data` (`httpx/_decoders.py`). |
| Truncated gzip/deflate bodies returned partial content with no error. | `flush()` raises `DecodingError` when the stream did not reach EOF. |
| Raw-deflate fallback failed when the first chunk was shorter than 2 bytes. | Header detection waits until 2 bytes are available. |
| zstd: multi-chunk streaming raised "cannot use a decompressobj multiple times"; an empty body behind `gzip, zstd` raised "incomplete". | The decompressor is only recreated at frame boundaries; empty input is a no-op. |
| `content=bytearray(...)`/`memoryview(...)` was treated as an iterable of ints; text-mode files were accepted and crashed later. | Both are handled as bytes; text-mode files raise `TypeError` up front. |
| Text-mode temp files were accepted on Windows because `tempfile.TemporaryFile(mode="w")` is not an `io.TextIOBase`. | `FileField` also inspects the `mode` attribute (`httpx/_multipart.py`). |
| A user-supplied `Content-Type: multipart/form-data` without a boundary was kept while the body used a random boundary; the 4-tuple `headers` dict was mutated; `X-Content-Type-Options` suppressed the part's Content-Type. | The stream content type always wins for multipart; headers are copied and matched by exact name. |
| Explicit `Transfer-Encoding: chunked` plus `content=` produced both `Transfer-Encoding` and `Content-Length` (forbidden by RFC 9112). | `Content-Length` is skipped when `Transfer-Encoding` is present. |
| `Headers() == None` was `True`, `Headers() == 123` raised, and `len(headers)` counted raw entries while iteration yielded unique keys. | Proper `__eq__` and `__len__` (`httpx/_models.py`). |
| `iter_bytes(chunk_size=0)` looped forever on empty chunks; negative sizes raised `IndexError`. | `chunk_size` is validated. |
| `Link` header parsing broke on `;` inside a URL and `=` inside a quoted value. | The parser splits on `>` and uses `split("=", 1)`. |
| `data={"k": b"bytes"}` was urlencoded as `k=b%27bytes%27`. | Bytes values are decoded as UTF-8. |
| A callable `default_encoding` was bypassed (and cached as utf-8) if `.encoding` was read before the body. | Encoding is not cached until content is available. |

### Client, redirects, proxies and auth

| Problem | Fix |
| --- | --- |
| `response.history` was corrupted when an auth retry followed a redirect (out of order, redirect hops missing). | History is carried forward from the intermediate response (`httpx/_client.py`). |
| Response event hooks ran before `response.history` was populated. | History is set before hooks run. |
| `base_url="https://x/api?token=1"` produced `https://x/api?token=1/path?x=2`. | Path and query are merged separately; base query params sit under request params. |
| Environment `HTTP_PROXY` silently overrode a user-supplied `mounts={"all://": ...}`. | User mounts take priority over environment-derived proxy mounts. |
| Client-level `params` overwrote a query embedded in the request URL. | Precedence is client params, then URL query, then explicit request params. |
| `Location: http:///path` dropped the request's port. | Host and port are copied from the original request. |
| Method-rewriting redirects (303, or 301/302 on POST) kept `Content-Type` after dropping the body. | `Content-Type` is stripped with the other body headers. |
| If the main transport's `close()` raised, mounted transports were never closed. | Every transport is closed and the first exception is re-raised. |
| `NO_PROXY=[::1]` or `NO_PROXY=fd00::/8` made `httpx.Client()` raise `InvalidURL`; `NO_PROXY=10.0.0.0/8` and `*.example.com` never matched anything. | Bracketed IPv6, IPv4/IPv6 CIDR and leading-`*` entries are parsed and matched (`httpx/_utils.py`). |
| `create_ssl_context(verify="ca.pem", cert="client.pem")` silently ignored `cert`. | The `verify=<str>` branch no longer returns early (`httpx/_config.py`). |
| `Timeout(Timeout(5), connect=1)` failed with a bare `AssertionError` and silently dropped `connect` under `python -O`. | `ValueError` with a message; tuple lengths are validated. |
| `Proxy(url_with_userinfo, auth=...)`: URL credentials silently beat the explicit argument. | Explicit `auth=` wins. |
| `DigestAuth`: an unknown algorithm raised `KeyError`; malformed challenge params raised `ValueError`/`IndexError`; param names were case-sensitive; a Digest challenge after `Basic` in the same header was missed; the cached challenge for host A was sent pre-emptively to host B; a `"` in credentials produced an unparsable header. | Tolerant challenge parsing, `ProtocolError` for bad input, `SHA-512-256` support, per-origin challenge cache, escaped quoted values (`httpx/_auth.py`). |
| `import httpx` eagerly imported click, rich and pygments when the `[cli]` extra was installed, doubling import time. | `httpx.main` is a lazy proxy that imports the CLI on first use. |
| Twelve `Client`/`AsyncClient` verb methods rejected `auth=None` in type checkers. | Annotations accept `None`. |

### URLs

| Problem | Fix |
| --- | --- |
| `URL("http://xn--zzzzzz.com").host` raised `idna.IDNAError`; `xn--` labels after the first were never decoded. | Any label is decoded; invalid punycode falls back to the raw host (`httpx/_urls.py`). |
| `URL("HTTP://example.com:80/")` kept port 80 because default-port normalization used the raw scheme. | The lowercased scheme is used (`httpx/_urlparse.py`). |
| Ports such as `-1`, `65536`, `1_0`, `+80` and fullwidth digits were accepted. | Ports must be ASCII digits in the range 0 to 65535. |
| `copy_with(netloc=b"[::1]:8080")` raised "Invalid port". | Bracketed IPv6 netlocs are parsed. |
| `copy_with(username="new")` dropped the existing password, and vice versa. | Only the named component changes. |
| `URL("http://x/a/b/..")` normalized to `/a` instead of `/a/` (RFC 3986 section 5.2.4). | Trailing dot segments keep the trailing slash. |
| A non-ASCII IPv6 zone id raised `UnicodeEncodeError`. | `InvalidURL` is raised. |
| `QueryParams` equality was order-insensitive but its hash was not; `URL("http://x") == "http://x:abc"` raised. | The hash uses sorted items; comparison with an invalid string is `False`. |

### Transports and CLI

| Problem | Fix |
| --- | --- |
| `WSGITransport`: chunked request bodies were invisible to apps (no `CONTENT_LENGTH`, `Transfer-Encoding` forwarded); `PATH_INFO` was not a PEP 3333 native string, so non-ASCII routes 404'd or crashed; the `write()` callable dropped data; the app iterable was not closed after `exc_info`; headers used ASCII instead of latin-1. | All fixed per PEP 3333 (`httpx/_transports/wsgi.py`). |
| `HTTPTransport(proxy=...)` silently dropped `retries`, `local_address`, `uds` and `socket_options`; `http1=False, http2=False` was accepted. | Options are passed to the proxy pools; `ValueError` when no protocol is enabled (`httpx/_transports/default.py`). |
| `ASGITransport`: an app that returned without finishing its response surfaced as a bare `AssertionError`; `scope["server"]` port was `None` for default ports. | A descriptive `RuntimeError`, or a 500 with `raise_app_exceptions=False`; default ports are filled in (`httpx/_transports/asgi.py`). |
| `MockTransport` responses never had `elapsed` set; bad handler return values gave confusing errors. | Pre-read responses are re-opened so the client times them; clear `TypeError`s (`httpx/_transports/mock.py`). |
| The CLI crashed on any non-ASCII header value, printed text bodies with unknown MIME types as binary data, escaped non-ASCII JSON, showed raw tracebacks for missing `h2`/`socksio` or a bad proxy scheme, silently ignored `-j` when `-c` was also given, and collapsed repeated `-d` keys. | latin-1 header handling, text fallback, `ensure_ascii=False`, one-line errors, body-option exclusivity, multi-value form data (`httpx/_main.py`). |

### Tests, docs, packaging and CI

| Problem | Fix |
| --- | --- |
| The suite had 5 failures on Windows (text-mode multipart, write timeout, uvicorn access logs captured by `caplog`), and CI only ran on Linux. | The multipart bug is fixed, the write-timeout test is skipped on Windows, the logging tests filter to the `httpx` logger, and CI gained Windows and macOS jobs. |
| The rewritten quickstart renumbered its headings, which broke anchors linked from other docs and from library docstrings, said `raise_for_status()` only raises for 4xx/5xx, and dropped the encoding, streaming-read, `next_request` and exception-attribute material. | Stable heading slugs are restored, the statement is corrected, the content is back, and four other pre-existing broken anchors are fixed. `mkdocs build --strict` passes. |
| Packaging and CI: no Python 3.14 classifier or CI leg, no `Typing :: Typed` classifier, the publish workflow used a long-lived PyPI token, no `permissions`/`concurrency`/`timeout-minutes`, scripts only knew `venv/bin`, and `chardet` was pinned to 5.2 although a test had been adapted for 6.0. | All updated; publishing uses PyPI trusted publishing. |

Run the checks locally with `scripts/check` and `scripts/test`. They now detect a Windows `venv/Scripts` layout.

## Installation

Install with pip:

```shell
$ pip install httpx
```

Or, to include the optional HTTP/2 support, use:

```shell
$ pip install httpx[http2]
```

HTTPX requires Python 3.9+.

## Documentation

Project documentation is available at [https://www.python-httpx.org/](https://www.python-httpx.org/).

For a run-through of all the basics, head over to the [QuickStart](https://www.python-httpx.org/quickstart/).

For more advanced topics, see the [Advanced Usage](https://www.python-httpx.org/advanced/) section, the [async support](https://www.python-httpx.org/async/) section, or the [HTTP/2](https://www.python-httpx.org/http2/) section.

The [Developer Interface](https://www.python-httpx.org/api/) provides a comprehensive API reference.

To find out about tools that integrate with HTTPX, see [Third Party Packages](https://www.python-httpx.org/third_party_packages/).

## Contribute

If you want to contribute with HTTPX check out the [Contributing Guide](https://www.python-httpx.org/contributing/) to learn how to start.

## Dependencies

The HTTPX project relies on these excellent libraries:

* `httpcore` - The underlying transport implementation for `httpx`.
  * `h11` - HTTP/1.1 support.
* `certifi` - SSL certificates.
* `idna` - Internationalized domain name support.
* `sniffio` - Async library autodetection.

As well as these optional installs:

* `h2` - HTTP/2 support. *(Optional, with `httpx[http2]`)*
* `socksio` - SOCKS proxy support. *(Optional, with `httpx[socks]`)*
* `rich` - Rich terminal support. *(Optional, with `httpx[cli]`)*
* `click` - Command line client support. *(Optional, with `httpx[cli]`)*
* `brotli` or `brotlicffi` - Decoding for "brotli" compressed responses. *(Optional, with `httpx[brotli]`)*
* `zstandard` - Decoding for "zstd" compressed responses. *(Optional, with `httpx[zstd]`)*

A huge amount of credit is due to `requests` for the API layout that
much of this work follows, as well as to `urllib3` for plenty of design
inspiration around the lower-level networking details.

---

<p align="center"><i>HTTPX is <a href="https://github.com/encode/httpx/blob/master/LICENSE.md">BSD licensed</a> code.<br/>Designed & crafted with care.</i><br/>&mdash; 🦋 &mdash;</p>
