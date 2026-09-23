from __future__ import annotations

import collections.abc
import warnings
from json import dumps as json_dumps
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Iterator,
    Mapping,
)
from urllib.parse import urlencode

from ._exceptions import StreamClosed, StreamConsumed
from ._multipart import MultipartStream, is_text_mode_file
from ._types import (
    AsyncByteStream,
    RequestContent,
    RequestData,
    RequestFiles,
    ResponseContent,
    SyncByteStream,
)
from ._utils import peek_filelike_length, primitive_value_to_str

__all__ = ["ByteStream"]


class ByteStream(AsyncByteStream, SyncByteStream):
    def __init__(self, stream: bytes) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        yield self._stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._stream


class IteratorByteStream(SyncByteStream):
    CHUNK_SIZE = 65_536

    def __init__(self, stream: Iterable[bytes]) -> None:
        self._stream = stream
        self._is_stream_consumed = False
        self._is_filelike = hasattr(stream, "read")
        # Any single-use iterator (generators included) cannot be replayed.
        # File-like objects are handled separately, since they are also
        # iterators but can be rewound.
        self._is_iterator = not self._is_filelike and isinstance(
            stream, collections.abc.Iterator
        )
        # For seekable file-like objects, remember where we started so that
        # the body can be replayed, e.g. on a redirect or an auth retry.
        self._start_offset: int | None = None
        if self._is_filelike and hasattr(stream, "seek") and hasattr(stream, "tell"):
            try:
                self._start_offset = stream.tell()
            except OSError:
                self._start_offset = None

    def __iter__(self) -> Iterator[bytes]:
        if self._is_stream_consumed and self._is_iterator:
            raise StreamConsumed()

        self._is_stream_consumed = True
        if self._is_filelike:
            # File-like interfaces should use 'read' directly.
            if self._start_offset is not None:
                self._stream.seek(self._start_offset)  # type: ignore[attr-defined]
            chunk = self._stream.read(self.CHUNK_SIZE)  # type: ignore[attr-defined]
            while chunk:
                yield chunk
                chunk = self._stream.read(self.CHUNK_SIZE)  # type: ignore[attr-defined]
        else:
            # Otherwise iterate.
            for part in self._stream:
                yield part


class AsyncIteratorByteStream(AsyncByteStream):
    CHUNK_SIZE = 65_536

    def __init__(self, stream: AsyncIterable[bytes]) -> None:
        self._stream = stream
        self._is_stream_consumed = False
        # Any single-use async iterator (async generators included) cannot
        # be replayed.
        self._is_iterator = not hasattr(stream, "aread") and isinstance(
            stream, collections.abc.AsyncIterator
        )

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if self._is_stream_consumed and self._is_iterator:
            raise StreamConsumed()

        self._is_stream_consumed = True
        if hasattr(self._stream, "aread"):
            # File-like interfaces should use 'aread' directly.
            chunk = await self._stream.aread(self.CHUNK_SIZE)
            while chunk:
                yield chunk
                chunk = await self._stream.aread(self.CHUNK_SIZE)
        else:
            # Otherwise iterate.
            async for part in self._stream:
                yield part


class UnattachedStream(AsyncByteStream, SyncByteStream):
    """
    If a request or response is serialized using pickle, then it is no longer
    attached to a stream for I/O purposes. Any stream operations should result
    in `httpx.StreamClosed`.
    """

    def __iter__(self) -> Iterator[bytes]:
        raise StreamClosed()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise StreamClosed()
        yield b""  # pragma: no cover


def encode_content(
    content: str | bytes | Iterable[bytes] | AsyncIterable[bytes],
) -> tuple[dict[str, str], SyncByteStream | AsyncByteStream]:
    if isinstance(content, (bytes, bytearray, memoryview, str)):
        body = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        content_length = len(body)
        headers = {"Content-Length": str(content_length)} if body else {}
        return headers, ByteStream(body)

    elif is_text_mode_file(content):
        raise TypeError(
            "Streaming request content from a file requires the file to be "
            "opened in binary mode, not text mode."
        )

    elif isinstance(content, Iterable) and not isinstance(content, dict):
        # `not isinstance(content, dict)` is a bit oddly specific, but it
        # catches a case that's easy for users to make in error, and would
        # otherwise pass through here, like any other bytes-iterable,
        # because `dict` happens to be iterable. See issue #2491.
        content_length_or_none = peek_filelike_length(
            content, from_current_position=True
        )

        if content_length_or_none is None:
            headers = {"Transfer-Encoding": "chunked"}
        else:
            headers = {"Content-Length": str(content_length_or_none)}
        return headers, IteratorByteStream(content)  # type: ignore

    elif isinstance(content, AsyncIterable):
        headers = {"Transfer-Encoding": "chunked"}
        return headers, AsyncIteratorByteStream(content)

    raise TypeError(f"Unexpected type for 'content', {type(content)!r}")


def _urlencoded_value(value: Any) -> str | bytes:
    """
    Coerce a form value for `urlencode`. Bytes are passed through untouched
    so that they are percent-encoded as-is, rather than via their `repr()`.
    """
    if isinstance(value, bytes):
        return value
    return primitive_value_to_str(value)


def encode_urlencoded_data(
    data: RequestData,
) -> tuple[dict[str, str], ByteStream]:
    plain_data: list[tuple[str, str | bytes]] = []
    for key, value in data.items():
        if isinstance(value, (list, tuple)):
            plain_data.extend([(key, _urlencoded_value(item)) for item in value])
        else:
            plain_data.append((key, _urlencoded_value(value)))
    body = urlencode(plain_data, doseq=True).encode("utf-8")
    content_length = str(len(body))
    content_type = "application/x-www-form-urlencoded"
    headers = {"Content-Length": content_length, "Content-Type": content_type}
    return headers, ByteStream(body)


def encode_multipart_data(
    data: RequestData, files: RequestFiles, boundary: bytes | None
) -> tuple[dict[str, str], MultipartStream]:
    multipart = MultipartStream(data=data, files=files, boundary=boundary)
    headers = multipart.get_headers()
    return headers, multipart


def encode_text(text: str) -> tuple[dict[str, str], ByteStream]:
    body = text.encode("utf-8")
    content_length = str(len(body))
    content_type = "text/plain; charset=utf-8"
    headers = {"Content-Length": content_length, "Content-Type": content_type}
    return headers, ByteStream(body)


def encode_html(html: str) -> tuple[dict[str, str], ByteStream]:
    body = html.encode("utf-8")
    content_length = str(len(body))
    content_type = "text/html; charset=utf-8"
    headers = {"Content-Length": content_length, "Content-Type": content_type}
    return headers, ByteStream(body)


def encode_json(json: Any) -> tuple[dict[str, str], ByteStream]:
    body = json_dumps(
        json, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    content_length = str(len(body))
    content_type = "application/json"
    headers = {"Content-Length": content_length, "Content-Type": content_type}
    return headers, ByteStream(body)


def encode_request(
    content: RequestContent | None = None,
    data: RequestData | None = None,
    files: RequestFiles | None = None,
    json: Any | None = None,
    boundary: bytes | None = None,
) -> tuple[dict[str, str], SyncByteStream | AsyncByteStream]:
    """
    Handles encoding the given `content`, `data`, `files`, and `json`,
    returning a two-tuple of (<headers>, <stream>).
    """
    if data is not None and not isinstance(data, Mapping):
        # We prefer to separate `content=<bytes|str|byte iterator|bytes aiterator>`
        # for raw request content, and `data=<form data>` for url encoded or
        # multipart form content.
        #
        # However for compat with requests, we *do* still support
        # `data=<bytes...>` usages. We deal with that case here, treating it
        # as if `content=<...>` had been supplied instead.
        message = "Use 'content=<...>' to upload raw bytes/text content."
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        return encode_content(data)

    if content is not None:
        return encode_content(content)
    elif files:
        return encode_multipart_data(data or {}, files, boundary)
    elif data:
        return encode_urlencoded_data(data)
    elif json is not None:
        return encode_json(json)

    return {}, ByteStream(b"")


def encode_response(
    content: ResponseContent | None = None,
    text: str | None = None,
    html: str | None = None,
    json: Any | None = None,
) -> tuple[dict[str, str], SyncByteStream | AsyncByteStream]:
    """
    Handles encoding the given `content`, returning a two-tuple of
    (<headers>, <stream>).
    """
    if content is not None:
        return encode_content(content)
    elif text is not None:
        return encode_text(text)
    elif html is not None:
        return encode_html(html)
    elif json is not None:
        return encode_json(json)

    return {}, ByteStream(b"")
