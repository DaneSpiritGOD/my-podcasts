"""HTTP access to the source site.

Kept behind a small interface so the pipeline can be tested with a fake
transport. Stdlib only, matching the rest of the project.

Every URL this module fetches ultimately comes from the Source Feed, which is
remote input. Without a scheme and host allowlist, a compromised or hijacked
feed could point us at ``file:///etc/hosts`` or a cloud metadata endpoint, and
the pipeline would copy the result into ``state.json``/``feed.xml`` — which the
workflow then commits to a public repository. The allowlist is the boundary
that makes that impossible.
"""

import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

TIMEOUT_SECONDS = 30

SOURCE_HOST = "commandline.microsoft.com"
SOURCE_FEED_URL = "https://{}/feed/".format(SOURCE_HOST)

# The only scheme and host the pipeline is ever allowed to talk to. Article
# links and Source URLs both live on the source site, so one host covers both.
ALLOWED_SCHEME = "https"
ALLOWED_HOSTS = frozenset({SOURCE_HOST})


class FetchError(Exception):
    """A request to the source site did not produce usable content."""

    def __init__(self, url: str, reason: str, status=None):
        self.url = url
        self.reason = reason
        self.status = status
        super().__init__("{}: {}".format(url, reason))


class BlockedURLError(FetchError):
    """A URL was refused before any request was made.

    Separate from a network failure because it is never transient: retrying
    cannot help, and a human should see it.
    """


def check_url(url: str) -> None:
    """Raise BlockedURLError unless ``url`` is an allowed source-site URL.

    Deliberately strict about the scheme: ``file:``, ``ftp:`` and ``data:`` are
    all reachable through urllib and all mean the pipeline is being pointed at
    something that is not the source site.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise BlockedURLError(url, "unparseable URL: {}".format(exc))

    if parsed.scheme != ALLOWED_SCHEME:
        raise BlockedURLError(
            url, "refusing scheme {!r}; only {} is allowed".format(parsed.scheme, ALLOWED_SCHEME)
        )

    # Normalise before comparing so "COMMANDLINE.MICROSOFT.COM" and a trailing
    # dot cannot slip past the allowlist.
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in ALLOWED_HOSTS:
        raise BlockedURLError(
            url,
            "refusing host {!r}; only {} is allowed".format(
                host, ", ".join(sorted(ALLOWED_HOSTS))
            ),
        )


class Transport:
    """The real network transport."""

    def get_text(self, url: str) -> str:
        check_url(url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            raise FetchError(url, "HTTP {}".format(exc.code), status=exc.code)
        except urllib.error.URLError as exc:
            raise FetchError(url, "connection failed: {}".format(exc.reason))
        except (TimeoutError, OSError) as exc:
            raise FetchError(url, "request failed: {}".format(exc))

    def probe(self, url: str) -> int:
        """Return the HTTP status of a HEAD request, or 0 if it cannot connect.

        A blocked URL returns 0: the Sentinel treats that as "unreachable", which
        is not something it opens an issue about.
        """
        try:
            check_url(url)
        except BlockedURLError:
            return 0
        request = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except urllib.error.URLError:
            return 0
        except (TimeoutError, OSError):
            return 0


def fetch_source_feed(transport) -> str:
    return transport.get_text(SOURCE_FEED_URL)


def fetch_article(transport, link: str) -> str:
    return transport.get_text(link)
