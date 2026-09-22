# HTTPX QuickStart

HTTPX is a Python library for making HTTP requests. It supports synchronous and asynchronous requests, making it useful for interacting with web services and APIs.

## 1. Making Your First Request

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

## 2. Making Different HTTP Requests

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

## 3. Passing Query Parameters

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

## 4. Reading Response Content

HTTPX provides several ways to access a response body.

### Text

```python
response = httpx.get("https://www.example.org")

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

## 5. Setting Custom Headers

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

## 6. Sending Data

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

## 7. Uploading Files

HTTPX supports multipart file uploads.

```python
with open("report.txt", "rb") as file:
    response = httpx.post(
        "https://httpbin.org/post",
        files={"file": file}
    )

print(response.status_code)
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

## 8. Handling Response Status Codes

You can inspect the status code or raise an exception when a request returns an unsuccessful HTTP status.

```python
response = httpx.get(
    "https://httpbin.org/status/404"
)

print(response.status_code)  # 404
```

Use `raise_for_status()` to handle unsuccessful responses:

```python
response = httpx.get(
    "https://httpbin.org/status/404"
)

response.raise_for_status()
```

This raises an `HTTPStatusError` for a 4xx or 5xx response.

For successful responses, the method returns the response object, allowing method chaining:

```python
data = httpx.get(
    "https://httpbin.org/get"
).raise_for_status().json()
```

## 9. Accessing Response Headers

Response headers provide information about the server's response.

```python
response = httpx.get(
    "https://httpbin.org/get"
)

print(response.headers)
print(response.headers.get("content-type"))
```

Header names are case-insensitive, so `Content-Type` and `content-type` refer to the same header.

## 10. Streaming Large Responses

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

Use `iter_raw()` when you need the raw response bytes without HTTP content decoding.

## 11. Working with Cookies

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

## 12. Following Redirects

HTTPX does not follow redirects by default.

```python
response = httpx.get(
    "http://github.com",
    follow_redirects=True
)

print(response.url)
print(response.history)
```

The `history` property contains the redirect responses followed before reaching the final response.

## 13. Configuring Timeouts

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

## 14. Authentication

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

## 15. Handling Exceptions

HTTPX provides exceptions that help you handle request failures.

### Request errors

```python
try:
    response = httpx.get(
        "https://www.example.com"
    )
except httpx.RequestError as exc:
    print(f"Request failed: {exc}")
```

### HTTP status errors

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

`RequestError` covers errors that occur while making a request, while `HTTPStatusError` is raised when `raise_for_status()` encounters an unsuccessful response.

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

For more advanced usage, explore HTTPX's asynchronous client, connection pooling, and transport configuration.
