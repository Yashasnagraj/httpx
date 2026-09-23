from __future__ import annotations

import gzip
import io
import typing
import zlib

import chardet
import pytest
import zstandard as zstd

import httpx
from httpx._decoders import ByteChunker, TextChunker


def test_deflate():
    """
    Deflate encoding may use either 'zlib' or 'deflate' in the wild.

    https://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib#answer-22311297
    """
    body = b"test 123"
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed_body = compressor.compress(body) + compressor.flush()

    headers = [(b"Content-Encoding", b"deflate")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_zlib():
    """
    Deflate encoding may use either 'zlib' or 'deflate' in the wild.

    https://stackoverflow.com/questions/1838699/how-can-i-decompress-a-gzip-stream-with-zlib#answer-22311297
    """
    body = b"test 123"
    compressed_body = zlib.compress(body)

    headers = [(b"Content-Encoding", b"deflate")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_gzip():
    body = b"test 123"
    compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    compressed_body = compressor.compress(body) + compressor.flush()

    headers = [(b"Content-Encoding", b"gzip")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_brotli():
    body = b"test 123"
    compressed_body = b"\x8b\x03\x80test 123\x03"

    headers = [(b"Content-Encoding", b"br")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_zstd():
    body = b"test 123"
    compressed_body = zstd.compress(body)

    headers = [(b"Content-Encoding", b"zstd")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_zstd_decoding_error():
    compressed_body = "this_is_not_zstd_compressed_data"

    headers = [(b"Content-Encoding", b"zstd")]
    with pytest.raises(httpx.DecodingError):
        httpx.Response(
            200,
            headers=headers,
            content=compressed_body,
        )


def test_zstd_empty():
    headers = [(b"Content-Encoding", b"zstd")]
    response = httpx.Response(200, headers=headers, content=b"")
    assert response.content == b""


def test_zstd_truncated():
    body = b"test 123"
    compressed_body = zstd.compress(body)

    headers = [(b"Content-Encoding", b"zstd")]
    with pytest.raises(httpx.DecodingError):
        httpx.Response(
            200,
            headers=headers,
            content=compressed_body[1:3],
        )


def test_zstd_multiframe():
    # test inspired by urllib3 test suite
    data = (
        # Zstandard frame
        zstd.compress(b"foo")
        # skippable frame (must be ignored)
        + bytes.fromhex(
            "50 2A 4D 18"  # Magic_Number (little-endian)
            "07 00 00 00"  # Frame_Size (little-endian)
            "00 00 00 00 00 00 00"  # User_Data
        )
        # Zstandard frame
        + zstd.compress(b"bar")
    )
    compressed_body = io.BytesIO(data)

    headers = [(b"Content-Encoding", b"zstd")]
    response = httpx.Response(200, headers=headers, content=compressed_body)
    response.read()
    assert response.content == b"foobar"


def test_multi():
    body = b"test 123"

    deflate_compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed_body = deflate_compressor.compress(body) + deflate_compressor.flush()

    gzip_compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    compressed_body = (
        gzip_compressor.compress(compressed_body) + gzip_compressor.flush()
    )

    headers = [(b"Content-Encoding", b"deflate, gzip")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


def test_multi_with_identity():
    body = b"test 123"
    compressed_body = b"\x8b\x03\x80test 123\x03"

    headers = [(b"Content-Encoding", b"br, identity")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body

    headers = [(b"Content-Encoding", b"identity, br")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compressed_body,
    )
    assert response.content == body


@pytest.mark.anyio
async def test_streaming():
    body = b"test 123"
    compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)

    async def compress(body: bytes) -> typing.AsyncIterator[bytes]:
        yield compressor.compress(body)
        yield compressor.flush()

    headers = [(b"Content-Encoding", b"gzip")]
    response = httpx.Response(
        200,
        headers=headers,
        content=compress(body),
    )
    assert not hasattr(response, "body")
    assert await response.aread() == body


@pytest.mark.parametrize("header_value", (b"deflate", b"gzip", b"br", b"identity"))
def test_empty_content(header_value):
    headers = [(b"Content-Encoding", header_value)]
    response = httpx.Response(
        200,
        headers=headers,
        content=b"",
    )
    assert response.content == b""


@pytest.mark.parametrize("header_value", (b"deflate", b"gzip", b"br", b"identity"))
def test_decoders_empty_cases(header_value):
    headers = [(b"Content-Encoding", header_value)]
    response = httpx.Response(content=b"", status_code=200, headers=headers)
    assert response.read() == b""


@pytest.mark.parametrize("header_value", (b"deflate", b"gzip", b"br"))
def test_decoding_errors(header_value):
    headers = [(b"Content-Encoding", header_value)]
    compressed_body = b"invalid"
    with pytest.raises(httpx.DecodingError):
        request = httpx.Request("GET", "https://example.org")
        httpx.Response(200, headers=headers, content=compressed_body, request=request)

    with pytest.raises(httpx.DecodingError):
        httpx.Response(200, headers=headers, content=compressed_body)


@pytest.mark.parametrize(
    ["data", "encoding"],
    [
        ((b"Hello,", b" world!"), "ascii"),
        ((b"\xe3\x83", b"\x88\xe3\x83\xa9", b"\xe3", b"\x83\x99\xe3\x83\xab"), "utf-8"),
        ((b"Euro character: \x88! abcdefghijklmnopqrstuvwxyz", b""), "cp1252"),
        ((b"Accented: \xd6sterreich abcdefghijklmnopqrstuvwxyz", b""), "iso-8859-1"),
    ],
)
@pytest.mark.anyio
async def test_text_decoder_with_autodetect(data, encoding):
    async def iterator() -> typing.AsyncIterator[bytes]:
        nonlocal data
        for chunk in data:
            yield chunk

    def autodetect(content):
        return chardet.detect(content).get("encoding")

    # Accessing `.text` on a read response.
    response = httpx.Response(200, content=iterator(), default_encoding=autodetect)
    await response.aread()
    assert response.text == (b"".join(data)).decode(encoding)

    # Streaming `.aiter_text` iteratively.
    # Note that if we streamed the text *without* having read it first, then
    # we won't get a `charset_normalizer` guess, and will instead always rely
    # on utf-8 if no charset is specified.
    text = "".join([part async for part in response.aiter_text()])
    assert text == (b"".join(data)).decode(encoding)


@pytest.mark.anyio
async def test_text_decoder_known_encoding():
    async def iterator() -> typing.AsyncIterator[bytes]:
        yield b"\x83g"
        yield b"\x83"
        yield b"\x89\x83x\x83\x8b"

    response = httpx.Response(
        200,
        headers=[(b"Content-Type", b"text/html; charset=shift-jis")],
        content=iterator(),
    )

    await response.aread()
    assert "".join(response.text) == "トラベル"


def test_text_decoder_empty_cases():
    response = httpx.Response(200, content=b"")
    assert response.text == ""

    response = httpx.Response(200, content=[b""])
    response.read()
    assert response.text == ""


@pytest.mark.parametrize(
    ["data", "expected"],
    [((b"Hello,", b" world!"), ["Hello,", " world!"])],
)
def test_streaming_text_decoder(
    data: typing.Iterable[bytes], expected: list[str]
) -> None:
    response = httpx.Response(200, content=iter(data))
    assert list(response.iter_text()) == expected


def test_line_decoder_nl():
    response = httpx.Response(200, content=[b""])
    assert list(response.iter_lines()) == []

    response = httpx.Response(200, content=[b"", b"a\n\nb\nc"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    # Issue #1033
    response = httpx.Response(
        200, content=[b"", b"12345\n", b"foo ", b"bar ", b"baz\n"]
    )
    assert list(response.iter_lines()) == ["12345", "foo bar baz"]


def test_line_decoder_cr():
    response = httpx.Response(200, content=[b"", b"a\r\rb\rc"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    response = httpx.Response(200, content=[b"", b"a\r\rb\rc\r"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    # Issue #1033
    response = httpx.Response(
        200, content=[b"", b"12345\r", b"foo ", b"bar ", b"baz\r"]
    )
    assert list(response.iter_lines()) == ["12345", "foo bar baz"]


def test_line_decoder_crnl():
    response = httpx.Response(200, content=[b"", b"a\r\n\r\nb\r\nc"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    response = httpx.Response(200, content=[b"", b"a\r\n\r\nb\r\nc\r\n"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    response = httpx.Response(200, content=[b"", b"a\r", b"\n\r\nb\r\nc"])
    assert list(response.iter_lines()) == ["a", "", "b", "c"]

    # Issue #1033
    response = httpx.Response(200, content=[b"", b"12345\r\n", b"foo bar baz\r\n"])
    assert list(response.iter_lines()) == ["12345", "foo bar baz"]


def test_invalid_content_encoding_header():
    headers = [(b"Content-Encoding", b"invalid-header")]
    body = b"test 123"

    response = httpx.Response(
        200,
        headers=headers,
        content=body,
    )
    assert response.content == body


def test_gzip_multi_member():
    """
    A gzip body may consist of several concatenated members (RFC 1952, 2.2).
    """
    compressed_body = gzip.compress(b"a") + gzip.compress(b"b")

    headers = [(b"Content-Encoding", b"gzip")]
    response = httpx.Response(200, headers=headers, content=compressed_body)
    assert response.content == b"ab"


def test_gzip_multi_member_streaming():
    first = gzip.compress(b"hello ")
    second = gzip.compress(b"world")
    # Split so that one chunk ends exactly on a member boundary, and another
    # straddles it.
    chunks = [first[:5], first[5:], second[:3], second[3:]]

    headers = [(b"Content-Encoding", b"gzip")]
    response = httpx.Response(200, headers=headers, content=iter(chunks))
    assert response.read() == b"hello world"

    chunks = [first[:5], first[5:] + second[:3], second[3:]]
    response = httpx.Response(200, headers=headers, content=iter(chunks))
    assert response.read() == b"hello world"


def test_gzip_truncated():
    compressed_body = gzip.compress(b"test 123")

    headers = [(b"Content-Encoding", b"gzip")]
    with pytest.raises(httpx.DecodingError, match="incomplete"):
        httpx.Response(200, headers=headers, content=compressed_body[:-4])


@pytest.mark.parametrize("wbits", [zlib.MAX_WBITS, -zlib.MAX_WBITS])
def test_deflate_truncated(wbits):
    compressor = zlib.compressobj(9, zlib.DEFLATED, wbits)
    compressed_body = compressor.compress(b"test 123" * 10) + compressor.flush()

    headers = [(b"Content-Encoding", b"deflate")]
    with pytest.raises(httpx.DecodingError, match="incomplete"):
        httpx.Response(200, headers=headers, content=compressed_body[:-4])


@pytest.mark.parametrize("wbits", [zlib.MAX_WBITS, -zlib.MAX_WBITS])
def test_deflate_streaming_single_byte_chunks(wbits):
    """
    zlib can only reject a stream as "not zlib-wrapped" once it has seen the
    two header bytes, so the raw-deflate fallback must still work when the
    first chunk is shorter than that.
    """
    body = b"test 123"
    compressor = zlib.compressobj(9, zlib.DEFLATED, wbits)
    compressed_body = compressor.compress(body) + compressor.flush()
    chunks = [compressed_body[i : i + 1] for i in range(len(compressed_body))]

    headers = [(b"Content-Encoding", b"deflate")]
    response = httpx.Response(200, headers=headers, content=iter(chunks))
    assert response.read() == body


def test_deflate_single_byte_body_is_incomplete():
    headers = [(b"Content-Encoding", b"deflate")]
    with pytest.raises(httpx.DecodingError, match="incomplete"):
        httpx.Response(200, headers=headers, content=b"K")


def test_zstd_streaming_chunks():
    # See https://github.com/encode/httpx/issues/3697
    data = zstd.ZstdCompressor().compress(b"a" * 100000)
    chunks = [data[:10], data[10:50], data[50:]]

    headers = [(b"Content-Encoding", b"zstd")]
    response = httpx.Response(200, headers=headers, content=iter(chunks))
    assert response.read() == b"a" * 100000


def test_zstd_multiframe_separate_chunks():
    chunks = [zstd.compress(b"hello "), zstd.compress(b"world")]

    headers = [(b"Content-Encoding", b"zstd")]
    response = httpx.Response(200, headers=headers, content=iter(chunks))
    assert response.read() == b"hello world"

    # ...and as a single body.
    response = httpx.Response(200, headers=headers, content=b"".join(chunks))
    assert response.content == b"hello world"


def test_multi_with_zstd_empty_content():
    headers = [(b"Content-Encoding", b"gzip, zstd")]
    response = httpx.Response(200, headers=headers, content=b"")
    assert response.content == b""


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_chunkers_reject_non_positive_chunk_size(chunk_size):
    with pytest.raises(ValueError):
        ByteChunker(chunk_size=chunk_size)
    with pytest.raises(ValueError):
        TextChunker(chunk_size=chunk_size)
