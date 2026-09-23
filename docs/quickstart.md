# HTTPX QuickStart

HTTPX is a Python library for making HTTP requests. It supports synchronous and asynchronous requests, making it useful for interacting with web services and APIs.

## Making Your First Request

First, import HTTPX:

```python
import httpx
```

Send a GET request to retrieve a webpage:

```python
response = httpx.get("https://httpbin.org/get")

print(response.status_code)  # 200
print(response.json())       # Response data
```

A `200` status code indicates that the request was successful.

## Making Different HTTP Requests

HTTPX provides convenient functions for common HTTP methods.

```python
# GET: Retrieve data
httpx.get("https://httpbin.org/get")

# POST: Submit data
httpx.post(
    "https://httpbin.org/post",
    data={"name": "Alex"}
)

# PUT: Update data
httpx.put(
    "https://httpbin.org/put",
    json={"name": "Alex"}
)

# DELETE: Delete a resource
httpx.delete("https://httpbin.org/delete")

# HEAD: Retrieve response headers
httpx.head("https://httpbin.org/get")

# OPTIONS: Check supported request methods
httpx.options("https://httpbin.org/get")
```

## Passing Query Parameters

Use the `params` argument to add query parameters to a URL. HTTPX automatically encodes them.

```python
params = {
    "search": "python",
    "page": 1
}

response = httpx.get(
    "https://httpbin.org/get",
    params=params
)

print(response.url)
```

You can also pass multiple values for the same parameter:

```python
params = {
    "tag": ["python", "httpx"]
}

response = httpx.get(
    "https://httpbin.org/get",
    params=params
)

print(response.url)
```

The resulting URL contains both values as repeated query parameters.

## Reading Response Content

HTTPX provides several ways to access a response body.

### Text

HTTPX will automatically handle decoding the response content into Unicode text.

```python
response = httpx.get("https://www.example.org")

print(response.text)
```

You can inspect what encoding will be used to decode the response:

```python
print(response.encoding)  # 'UTF-8'
```

In some cases the response may not contain an explicit encoding, in which case
`response.encoding` is `None` and HTTPX will attempt to automatically determine
an encoding to use. If you need to override the standard behaviour and
explicitly set the encoding, do so before accessing `.text`:

```python
response.encoding = "ISO-8859-1"

print(response.text)
```

### JSON

```python
response = httpx.get(
    "https://api.github.com/events"
)

data = response.json()
print(data)
```

### Binary content

```python
response = httpx.get("https://www.example.org")

content = response.content
print(content)
```

Binary content is useful when working with images, documents, and other non-text responses.

Any `gzip` and `deflate` HTTP response encodings will automatically be decoded
for you. If `brotli` is installed, then the `brotli` response encoding will be
supported. If `zstandard` is installed, then `zstd` response encodings will
also be supported.

## Setting Custom Headers

Headers allow you to send additional information with a request.

```python
headers = {
    "User-Agent": "my-app/1.0"
}

response = httpx.get(
    "https://httpbin.org/headers",
    headers=headers
)

print(response.json())
```

## Sending Data

HTTPX supports form data, JSON, and raw binary content.

### Form-encoded data

```python
data = {
    "username": "alex",
    "role": "developer"
}

response = httpx.post(
    "https://httpbin.org/post",
    data=data
)
```

### JSON data

```python
payload = {
    "name": "Alex",
    "active": True,
    "skills": ["Python", "HTTPX"]
}

response = httpx.post(
    "https://httpbin.org/post",
    json=payload
)
```

### Binary data

```python
content = b"Hello, world!"

response = httpx.post(
    "https://httpbin.org/post",
    content=content
)
```

Use `data=` for form submissions, `json=` for JSON payloads, and `content=` for raw bytes.

## Sending Multipart File Uploads

HTTPX supports multipart file uploads.

```python
with open("report.txt", "rb") as file:
    response = httpx.post(
        "https://httpbin.org/post",
        files={"file": file}
    )

print(response.status_code)
```

You can also explicitly set the filename and content type, by using a tuple
of items for the file value:

```python
with open("report.xls", "rb") as file:
    files = {
        "upload-file": ("report.xls", file, "application/vnd.ms-excel")
    }
    response = httpx.post(
        "https://httpbin.org/post",
        files=files
    )
```

You can also include regular form fields alongside uploaded files:

```python
with open("report.txt", "rb") as file:
    response = httpx.post(
        "https://httpbin.org/post",
        data={"description": "Monthly report"},
        files={"file": file}
    )
```

## Handling Response Status Codes

You can inspect the status code or raise an exception when a request returns an unsuccessful HTTP status.

```python
response = httpx.get(
    "https://httpbin.org/status/404"
)

print(response.status_code)  # 404
```

HTTPX also includes an easy shortcut for accessing status codes by their text phrase:

```python
print(response.status_code == httpx.codes.NOT_FOUND)  # True
```

Use `raise_for_status()` to handle unsuccessful responses:

```python
response = httpx.get(
    "https://httpbin.org/status/404"
)

response.raise_for_status()
```

This raises an `HTTPStatusError` for any response that is not a 2xx success
code. That includes 4xx client errors and 5xx server errors, but also 1xx
informational responses and 3xx redirects. In particular, because HTTPX does
not follow redirects by default, a 3xx response will raise unless you pass
`follow_redirects=True` (see [Following Redirects](#following-redirects)).

For successful responses, the method returns the response object, allowing method chaining:

```python
data = httpx.get(
    "https://httpbin.org/get"
).raise_for_status().json()
```

## Accessing Response Headers

Response headers provide information about the server's response.

```python
response = httpx.get(
    "https://httpbin.org/get"
)

print(response.headers)
print(response.headers.get("content-type"))
```

Header names are case-insensitive, so `Content-Type` and `content-type` refer to the same header.

Multiple values for a single response header are represented as a single comma-separated value, as per [RFC 7230](https://tools.ietf.org/html/rfc7230#section-3.2).

## Streaming Responses

For large downloads, streaming lets you process the response incrementally instead of loading the entire body into memory.

```python
with httpx.stream(
    "GET",
    "https://www.example.com"
) as response:
    response.raise_for_status()

    for chunk in response.iter_bytes():
        print(chunk)
```

You can also stream text or individual lines:

```python
with httpx.stream(
    "GET",
    "https://www.example.com"
) as response:
    for line in response.iter_lines():
        print(line)
```

HTTPX will use universal line endings, normalising all cases to `\n`.

Use `iter_raw()` when you need the raw response bytes without HTTP content decoding.

If you're using streaming responses in any of these ways then the
`response.content` and `response.text` attributes will not be available, and
will raise errors if accessed. However you can also use the response streaming
functionality to conditionally load the response body, by calling
`response.read()` first:

```python
with httpx.stream(
    "GET",
    "https://www.example.com"
) as response:
    if int(response.headers["Content-Length"]) < TOO_LONG:
        response.read()
        print(response.text)
```

## Working with Cookies

Cookies can be read from responses or sent with requests.

```python
response = httpx.get(
    "https://httpbin.org/cookies/set?theme=dark"
)

print(response.cookies)
```

To send cookies:

```python
cookies = {
    "theme": "dark"
}

response = httpx.get(
    "https://httpbin.org/cookies",
    cookies=cookies
)

print(response.json())
```

## Following Redirects

HTTPX does not follow redirects by default. When a redirect response is
returned, the `next_request` property holds the request that would be sent
next if redirects were being followed:

```python
response = httpx.get("http://github.com")

print(response.status_code)   # 301
print(response.history)       # []
print(response.next_request)  # <Request('GET', 'https://github.com/')>
```

You can enable redirect handling with the `follow_redirects` parameter:

```python
response = httpx.get(
    "http://github.com",
    follow_redirects=True
)

print(response.url)
print(response.history)
```

The `history` property contains the redirect responses followed before reaching the final response.

## Timeouts

HTTPX uses a default network inactivity timeout of five seconds.

You can configure a different timeout:

```python
response = httpx.get(
    "https://www.example.com",
    timeout=10.0
)
```

To disable timeouts:

```python
response = httpx.get(
    "https://www.example.com",
    timeout=None
)
```

For production applications, configure timeouts according to the needs of your service.
For advanced timeout management, see [Timeout fine-tuning](advanced/timeouts.md#fine-tuning-the-configuration).

## Authentication

HTTPX supports Basic and Digest authentication.

### Basic authentication

```python
response = httpx.get(
    "https://example.com",
    auth=("username", "password")
)
```

### Digest authentication

```python
auth = httpx.DigestAuth(
    "username",
    "password"
)

response = httpx.get(
    "https://example.com",
    auth=auth
)
```

Use real credentials only with trusted services and secure HTTPS connections.

## Exceptions

HTTPX provides exceptions that help you handle request failures.

### Request errors

The `RequestError` class is a superclass that encompasses any exception that
occurs while issuing an HTTP request. These exceptions include a `.request`
attribute.

```python
try:
    response = httpx.get(
        "https://www.example.com"
    )
except httpx.RequestError as exc:
    print(f"An error occurred while requesting {exc.request.url!r}.")
```

### HTTP status errors

The `HTTPStatusError` class is raised by `response.raise_for_status()` on
responses which are not a 2xx success code. These exceptions include both a
`.request` and a `.response` attribute.

```python
try:
    response = httpx.get(
        "https://httpbin.org/status/404"
    )
    response.raise_for_status()
except httpx.HTTPStatusError as exc:
    print(
        f"HTTP {exc.response.status_code}: "
        f"{exc.response.url}"
    )
```

There is also a base class `HTTPError` that includes both of these categories,
and can be used to catch either failed requests or unsuccessful responses.

For a full list of available exceptions, see [Exceptions (API Reference)](exceptions.md).

---

## Quick Reference

| Requirement           | HTTPX option            |
| --------------------- | ----------------------- |
| Retrieve data         | `httpx.get()`           |
| Submit form data      | `data=`                 |
| Send JSON             | `json=`                 |
| Upload files          | `files=`                |
| Add query parameters  | `params=`               |
| Set request headers   | `headers=`              |
| Configure timeout     | `timeout=`              |
| Follow redirects      | `follow_redirects=True` |
| Check response status | `raise_for_status()`    |
| Stream a response     | `httpx.stream()`        |

## Next Steps

- [Async Support](async.md) for using HTTPX with `asyncio`, `trio` or `anyio`.
- [Clients](advanced/clients.md) for connection pooling and sharing configuration across requests.
- [Timeout fine-tuning](advanced/timeouts.md#fine-tuning-the-configuration) for per-phase timeout configuration.
