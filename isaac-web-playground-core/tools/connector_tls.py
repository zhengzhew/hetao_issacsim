"""Verify HTTPS and WSS with the user-provided CA for one server origin."""
from http.client import HTTPSConnection
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, build_opener


def ssl_context(url):
    context = ssl.create_default_context()
    parsed = urlsplit(url)
    if (parsed.scheme in ('https', 'wss') and parsed.hostname == '10.72.255.16'
            and parsed.port in (None, 443)):
        resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        context.load_verify_locations(cafile=str(resources / 'certificates/10.72.255.16-root.crt'))
    return context


class ConnectorHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        # Select trust for each URL, including a redirected request's new origin.
        return self.do_open(HTTPSConnection, req, context=ssl_context(req.full_url))


def open_url(request, timeout=5):
    return build_opener(ConnectorHTTPSHandler()).open(request, timeout=timeout)


def websocket_ssl_options(url):
    return {'context': ssl_context(url)} if urlsplit(url).scheme == 'wss' else {}
