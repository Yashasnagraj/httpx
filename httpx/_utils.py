from __future__ import annotations

import ipaddress
import os
import re
import stat
import typing
from urllib.request import getproxies

from ._types import PrimitiveData

if typing.TYPE_CHECKING:  # pragma: no cover
    from ._urls import URL


def primitive_value_to_str(value: PrimitiveData) -> str:
    """
    Coerce a primitive data type into a string value.

    Note that we prefer JSON-style 'true'/'false' for boolean values here.
    """
    if value is True:
        return "true"
    elif value is False:
        return "false"
    elif value is None:
        return ""
    return str(value)


def get_environment_proxies() -> dict[str, str | None]:
    """Gets proxy information from the environment"""

    # urllib.request.getproxies() falls back on System
    # Registry and Config for proxies on Windows and macOS.
    # We don't want to propagate non-HTTP proxies into
    # our configuration such as 'TRAVIS_APT_PROXY'.
    proxy_info = getproxies()
    mounts: dict[str, str | None] = {}

    for scheme in ("http", "https", "all"):
        if proxy_info.get(scheme):
            hostname = proxy_info[scheme]
            mounts[f"{scheme}://"] = (
                hostname if "://" in hostname else f"http://{hostname}"
            )

    no_proxy_hosts = [host.strip() for host in proxy_info.get("no", "").split(",")]
    for hostname in no_proxy_hosts:
        # See https://curl.haxx.se/libcurl/c/CURLOPT_NOPROXY.html for details
        # on how names in `NO_PROXY` are handled.
        if hostname == "*":
            # If NO_PROXY=* is used or if "*" occurs as any one of the comma
            # separated hostnames, then we should just bypass any information
            # from HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, and always ignore
            # proxies.
            return {}
        elif hostname:
            # NO_PROXY=.google.com is marked as "all://*.google.com,
            #   which disables "www.google.com" but not "google.com"
            # NO_PROXY=google.com is marked as "all://*google.com,
            #   which disables "www.google.com" and "google.com".
            #   (But not "wwwgoogle.com")
            # NO_PROXY can include domains, IPv6, IPv4 addresses and "localhost"
            #   NO_PROXY=example.com,::1,localhost,192.168.0.0/16
            # CIDR ranges such as "10.0.0.0/8" or "fd00::/8" are supported by
            #   `URLPattern`, which matches any address within the network.
            if "://" in hostname:
                mounts[hostname] = None
            elif hostname.startswith("["):
                # Bracketed IPv6, optionally with a port: "[::1]" or "[::1]:8080".
                # The brackets are already present, so pass the entry through
                # unchanged rather than wrapping it in a second pair.
                mounts[f"all://{hostname}"] = None
            elif is_ipv4_hostname(hostname):
                mounts[f"all://{hostname}"] = None
            elif is_ipv6_hostname(hostname):
                # An IPv6 address must be bracketed to be a valid URL host, and
                # any CIDR prefix ("fd00::/8") has to sit outside the brackets.
                address, slash, prefix = hostname.partition("/")
                mounts[f"all://[{address}]{slash}{prefix}"] = None
            elif hostname.lower() == "localhost":
                mounts[f"all://{hostname}"] = None
            else:
                # NO_PROXY=*.google.com is equivalent to NO_PROXY=.google.com,
                #   so drop any leading "*" before we add our own wildcard.
                hostname = hostname.lstrip("*")
                if hostname:
                    mounts[f"all://*{hostname}"] = None

    return mounts


def to_bytes(value: str | bytes, encoding: str = "utf-8") -> bytes:
    return value.encode(encoding) if isinstance(value, str) else value


def to_str(value: str | bytes, encoding: str = "utf-8") -> str:
    return value if isinstance(value, str) else value.decode(encoding)


def to_bytes_or_str(value: str, match_type_of: typing.AnyStr) -> typing.AnyStr:
    return value if isinstance(match_type_of, str) else value.encode()


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def peek_filelike_length(
    stream: typing.Any, *, from_current_position: bool = False
) -> int | None:
    """
    Given a file-like stream object, return its length in number of bytes
    without reading it into memory.

    By default this is the total size of the stream. When `from_current_position`
    is set, the bytes before the stream's current position are excluded, so the
    result is the number of bytes that a `.read()` from here would return.

    Returns `None` if the length cannot be determined, in which case callers
    should fall back to chunked transfer encoding.
    """
    try:
        # Is it an actual file?
        fd = stream.fileno()
        # Yup, seems to be an actual file.
        st = os.fstat(fd)
    except (AttributeError, OSError):
        # No... Maybe it's something that supports random access, like `io.BytesIO`?
        try:
            # Assuming so, go to end of stream to figure out its length,
            # then put it back in place.
            offset = stream.tell()
            length: int = stream.seek(0, os.SEEK_END)
            stream.seek(offset)
        except (AttributeError, OSError):
            # Not even that? Sorry, we're doomed...
            return None
    else:
        if not stat.S_ISREG(st.st_mode):
            # `st_size` is only meaningful for regular files. For pipes,
            # sockets, character devices and the like it is zero or garbage,
            # so report an unknown length and let chunked encoding handle it.
            return None
        length = st.st_size

    if from_current_position:
        try:
            offset = stream.tell()
        except (AttributeError, OSError):
            # The stream can't report its position, so we can't tell how much
            # of it has already been consumed.
            return None
        length = max(length - offset, 0)

    return length


class URLPattern:
    """
    A utility class currently used for making lookups against proxy keys...

    # Wildcard matching...
    >>> pattern = URLPattern("all://")
    >>> pattern.matches(httpx.URL("http://example.com"))
    True

    # Witch scheme matching...
    >>> pattern = URLPattern("https://")
    >>> pattern.matches(httpx.URL("https://example.com"))
    True
    >>> pattern.matches(httpx.URL("http://example.com"))
    False

    # With domain matching...
    >>> pattern = URLPattern("https://example.com")
    >>> pattern.matches(httpx.URL("https://example.com"))
    True
    >>> pattern.matches(httpx.URL("http://example.com"))
    False
    >>> pattern.matches(httpx.URL("https://other.com"))
    False

    # Wildcard scheme, with domain matching...
    >>> pattern = URLPattern("all://example.com")
    >>> pattern.matches(httpx.URL("https://example.com"))
    True
    >>> pattern.matches(httpx.URL("http://example.com"))
    True
    >>> pattern.matches(httpx.URL("https://other.com"))
    False

    # With port matching...
    >>> pattern = URLPattern("https://example.com:1234")
    >>> pattern.matches(httpx.URL("https://example.com:1234"))
    True
    >>> pattern.matches(httpx.URL("https://example.com"))
    False
    """

    def __init__(self, pattern: str) -> None:
        from ._urls import URL

        if pattern and ":" not in pattern:
            raise ValueError(
                f"Proxy keys should use proper URL forms rather "
                f"than plain scheme strings. "
                f'Instead of "{pattern}", use "{pattern}://"'
            )

        url = URL(pattern)
        self.pattern = pattern
        self.scheme = "" if url.scheme == "all" else url.scheme
        self.host = "" if url.host == "*" else url.host
        self.port = url.port
        self.network = self._parse_network(url)
        if not url.host or url.host == "*":
            self.host_regex: typing.Pattern[str] | None = None
        elif url.host.startswith("*."):
            # *.example.com should match "www.example.com", but not "example.com"
            domain = re.escape(url.host[2:])
            self.host_regex = re.compile(f"^.+\\.{domain}$")
        elif url.host.startswith("*"):
            # *example.com should match "www.example.com" and "example.com"
            domain = re.escape(url.host[1:])
            self.host_regex = re.compile(f"^(.+\\.)?{domain}$")
        else:
            # example.com should match "example.com" but not "www.example.com"
            domain = re.escape(url.host)
            self.host_regex = re.compile(f"^{domain}$")

    @staticmethod
    def _parse_network(
        url: URL,
    ) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
        """
        A pattern such as "all://10.0.0.0/8" or "all://[fd00::]/8" parses as an
        IP address host with the CIDR prefix length left over in the path.
        Recognise that form and return the network it describes, or `None`
        if the pattern is not an IP network.
        """
        prefix = url.path[1:]
        if not (url.host and url.path.startswith("/") and prefix.isdigit()):
            return None
        try:
            network = ipaddress.ip_network(f"{url.host}/{prefix}", strict=False)
        except ValueError:
            return None
        if network.prefixlen == network.max_prefixlen:
            # A full-length prefix is just a single address, which is
            # handled by the regular exact host match.
            return None
        return network

    def matches(self, other: URL) -> bool:
        if self.scheme and self.scheme != other.scheme:
            return False
        if self.network is not None:
            try:
                address = ipaddress.ip_address(other.host)
            except ValueError:
                return False
            if address not in self.network:
                return False
        elif (
            self.host
            and self.host_regex is not None
            and not self.host_regex.match(other.host)
        ):
            return False
        if self.port is not None and self.port != other.port:
            return False
        return True

    @property
    def priority(self) -> tuple[int, int, int]:
        """
        The priority allows URLPattern instances to be sortable, so that
        we can match from most specific to least specific.
        """
        # URLs with a port should take priority over URLs without a port.
        port_priority = 0 if self.port is not None else 1
        # Longer hostnames should match first.
        host_priority = -len(self.host)
        # Longer schemes should match first.
        scheme_priority = -len(self.scheme)
        return (port_priority, host_priority, scheme_priority)

    def __hash__(self) -> int:
        return hash(self.pattern)

    def __lt__(self, other: URLPattern) -> bool:
        return self.priority < other.priority

    def __eq__(self, other: typing.Any) -> bool:
        return isinstance(other, URLPattern) and self.pattern == other.pattern


def is_ipv4_hostname(hostname: str) -> bool:
    try:
        ipaddress.IPv4Address(hostname.split("/")[0])
    except Exception:
        return False
    return True


def is_ipv6_hostname(hostname: str) -> bool:
    try:
        ipaddress.IPv6Address(hostname.split("/")[0])
    except Exception:
        return False
    return True
