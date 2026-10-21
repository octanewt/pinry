"""Fetch images from user-supplied URLs without exposing internal services.

Every connection resolves the host itself, refuses non-public addresses
(unless ``ALLOW_PRIVATE_URL_FETCH`` is set) and connects to the address it
checked, so a DNS answer can't change between the check and the connect.
Redirects are followed by hand and each hop goes through the same check.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
from urllib3.util import connection as urllib3_connection

USER_AGENT = "Mozilla/5.0 (compatible; Pinry; +https://github.com/pinry/pinry)"
TIMEOUT = (5, 15)
MAX_REDIRECTS = 3
DEFAULT_MAX_FETCH_BYTES = 50 * 1024 * 1024
REDIRECT_STATUSES = (301, 302, 303, 307, 308)
NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
CHUNK_SIZE = 64 * 1024


class FetchError(Exception):
    """The URL could not be fetched; the message is safe to show users."""


class BlockedAddressError(FetchError):
    pass


def _max_fetch_bytes():
    return getattr(settings, "MAX_FETCH_BYTES", DEFAULT_MAX_FETCH_BYTES)


def _private_fetch_allowed():
    return getattr(settings, "ALLOW_PRIVATE_URL_FETCH", False)


def is_public_address(ip):
    ip = ipaddress.ip_address(ip)
    if ip.version == 6:
        # Addresses that embed an IPv4 address are judged by that address.
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and ip.teredo:
            embedded = ip.teredo[1]
        if embedded is None and ip in NAT64_PREFIX:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            return is_public_address(embedded)
    return ip.is_global and not (
        ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def resolve(host, port):
    """Return the addresses to connect to, refusing any non-public one."""
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise FetchError("Could not fetch the image.")
    addresses = []
    for family, _, _, _, sockaddr in infos:
        # Drop an IPv6 zone id ("fe80::1%eth0") before parsing.
        address = sockaddr[0].split("%")[0]
        if not _private_fetch_allowed() and not is_public_address(address):
            raise BlockedAddressError(
                "The URL points to an address Pinry is not allowed to fetch."
            )
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise FetchError("Could not fetch the image.")
    return addresses


class _CheckedConnectionMixin(object):
    def _new_conn(self):
        extra_kw = {}
        if self.source_address:
            extra_kw["source_address"] = self.source_address
        if self.socket_options:
            extra_kw["socket_options"] = self.socket_options

        # TLS (SNI and certificate checks) still uses self.host; only the
        # TCP connection goes to the address checked here.
        last_error = None
        for address in resolve(self.host, self.port):
            try:
                return urllib3_connection.create_connection(
                    (address, self.port), self.timeout, **extra_kw
                )
            except socket.timeout:
                raise ConnectTimeoutError(
                    self, "Connection to %s timed out." % self.host
                )
            except socket.error as e:
                last_error = e
        raise NewConnectionError(
            self, "Failed to establish a new connection: %s" % last_error
        )


class _CheckedHTTPConnection(_CheckedConnectionMixin, HTTPConnection):
    pass


class _CheckedHTTPSConnection(_CheckedConnectionMixin, HTTPSConnection):
    pass


class _CheckedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _CheckedHTTPConnection


class _CheckedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _CheckedHTTPSConnection


class CheckedAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        super(CheckedAdapter, self).init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": _CheckedHTTPConnectionPool,
            "https": _CheckedHTTPSConnectionPool,
        }


def _check_scheme(url):
    if urlparse(url).scheme.lower() not in ("http", "https"):
        raise FetchError("Only http and https URLs can be fetched.")


def _new_session():
    session = requests.Session()
    # No proxies from the environment (the check would see the proxy's
    # address, not the target's) and no credentials from ~/.netrc.
    session.trust_env = False
    adapter = CheckedAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _read_body(response, limit):
    length = response.headers.get("Content-Length")
    if length is not None and length.isdigit() and int(length) > limit:
        raise FetchError("The image is too large.")
    body = bytearray()
    for chunk in response.iter_content(CHUNK_SIZE):
        body.extend(chunk)
        if len(body) > limit:
            raise FetchError("The image is too large.")
    return bytes(body)


def fetch_url(url, referer=None):
    """Return the body of ``url`` as bytes, or raise FetchError."""
    headers = {"User-Agent": USER_AGENT}
    if referer is not None:
        headers["Referer"] = referer
    limit = _max_fetch_bytes()
    with _new_session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            _check_scheme(url)
            try:
                response = session.get(
                    url, headers=headers, timeout=TIMEOUT,
                    stream=True, allow_redirects=False,
                )
            except requests.RequestException:
                raise FetchError("Could not fetch the image.")
            with response:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("Location")
                    if not location:
                        raise FetchError("Could not fetch the image.")
                    url = urljoin(url, location)
                    continue
                if not 200 <= response.status_code < 300:
                    raise FetchError("Could not fetch the image.")
                try:
                    return _read_body(response, limit)
                except requests.RequestException:
                    raise FetchError("Could not fetch the image.")
    raise FetchError("Too many redirects.")
