import http.client
import ipaddress
import re
import socket
import ssl
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException

from ..repositories import search_settings

MAX_PAGE_BYTES = 2_000_000
MAX_PAGE_CHARS = 12_000
MAX_RESULTS = 5


class WebToolError(Exception):
    pass


def search_web(query):
    if not isinstance(query, str):
        raise WebToolError('Search query must be text.')
    query = query.strip()
    if not query or len(query) > 500:
        raise WebToolError('Search query must be between 1 and 500 characters.')
    api_key = search_settings.get_tavily_api_key()
    if api_key:
        try:
            with httpx.Client(timeout=15, trust_env=False) as client:
                response = client.post(
                    'https://api.tavily.com/search',
                    json={
                        'api_key': api_key,
                        'query': query,
                        'max_results': MAX_RESULTS,
                        'search_depth': 'basic',
                    },
                )
            if not response.is_success:
                raise WebToolError(
                    f'Tavily search failed (HTTP {response.status_code}). '
                    'Check the Tavily API key and try again.'
                )
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get('results', []), list):
                raise WebToolError('Tavily returned an invalid search response.')
            results = payload.get('results', [])
            answer = payload.get('answer')
            provider = 'Tavily'
        except (httpx.HTTPError, ValueError) as exc:
            raise WebToolError('Could not complete the Tavily search request.') from exc
    else:
        try:
            results = list(DDGS().text(query, max_results=MAX_RESULTS))
            answer = None
            provider = 'DDGS'
        except (DDGSException, RatelimitException) as exc:
            raise WebToolError('The DDGS search provider could not complete the search.') from exc

    normalized = []
    for result in results[:MAX_RESULTS]:
        if not isinstance(result, dict):
            continue
        url = result.get('url') or result.get('href')
        title = result.get('title')
        snippet = result.get('content') or result.get('body') or result.get('snippet')
        if not isinstance(url, str) or not isinstance(title, str):
            continue
        normalized.append({
            'title': title[:500],
            'url': url[:2000],
            'snippet': snippet[:2000] if isinstance(snippet, str) else '',
        })
    return {
        'query': query,
        'provider': provider,
        'summary': answer.strip()[:4000] if isinstance(answer, str) and answer.strip() else '',
        'results': normalized,
    }


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.description = ''
        self.text = []
        self.skip_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('script', 'style', 'noscript', 'svg', 'iframe', 'template'):
            self.skip_depth += 1
        if tag == 'title':
            self.in_title = True
        meta_name = (attributes.get('name') or attributes.get('property') or '').lower()
        if tag == 'meta' and meta_name in ('description', 'og:description'):
            self.description = attributes.get('content', '')[:1000]
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'section', 'article'):
            self.text.append('\n')

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        if tag in ('script', 'style', 'noscript', 'svg', 'iframe', 'template') and self.skip_depth:
            self.skip_depth -= 1
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'section', 'article'):
            self.text.append('\n')

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = ' '.join(data.split())
        if not text:
            return
        if self.in_title:
            self.title.append(text)
        else:
            self.text.append(f' {text} ')


def _validated_public_address(host, port):
    try:
        address = ipaddress.ip_address(host)
        addresses = [address]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            ]
        except socket.gaierror as exc:
            raise WebToolError('The page host could not be resolved.') from exc
    addresses = [
        address.ipv4_mapped if address.version == 6 and address.ipv4_mapped else address
        for address in addresses
    ]
    if not addresses or any(not address.is_global for address in addresses):
        raise WebToolError('Only publicly accessible web pages can be scraped.')
    return str(addresses[0])


def scrape_page(url):
    if not isinstance(url, str) or len(url) > 2000:
        raise WebToolError('Provide a valid public web page URL.')
    try:
        parsed = urlsplit(url.strip())
        requested_port = parsed.port
    except ValueError as exc:
        raise WebToolError('Provide a valid public web page URL.') from exc
    if (
        parsed.scheme not in ('http', 'https')
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or requested_port not in (None, 443 if parsed.scheme == 'https' else 80)
    ):
        raise WebToolError('Only public HTTP or HTTPS page URLs on standard ports are supported.')
    port = requested_port or (443 if parsed.scheme == 'https' else 80)
    address = _validated_public_address(parsed.hostname, port)
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    host = (
        parsed.hostname.lower()
        if ':' in parsed.hostname
        else parsed.hostname.encode('idna').decode('ascii')
    )
    host_header = f'[{host}]' if ':' in host else host
    if parsed.port:
        host_header += f':{parsed.port}'
    request_path = quote(path, safe="/%:@!$&'()*+,;=-._~?")
    request = (
        f'GET {request_path} HTTP/1.0\r\n'
        f'Host: {host_header}\r\n'
        'User-Agent: OmniAgent/1.0 (page extraction)\r\n'
        'Accept: text/html,text/plain;q=0.9\r\n'
        'Accept-Encoding: identity\r\n'
        'Connection: close\r\n\r\n'
    ).encode('ascii')
    raw_socket = None
    try:
        raw_socket = socket.create_connection((address, port), timeout=12)
        connection = (
            ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
            if parsed.scheme == 'https'
            else raw_socket
        )
        connection.settimeout(12)
        connection.sendall(request)
        response = http.client.HTTPResponse(connection)
        response.begin()
        if response.status < 200 or response.status >= 300:
            raise WebToolError(f'Page request failed (HTTP {response.status}).')
        content_type = response.getheader('Content-Type', '').lower()
        if 'text/html' not in content_type and 'text/plain' not in content_type:
            raise WebToolError('The URL did not return an HTML or plain-text page.')
        content_length = response.getheader('Content-Length')
        if content_length and int(content_length) > MAX_PAGE_BYTES:
            raise WebToolError('The page is too large to extract safely.')
        page = response.read(MAX_PAGE_BYTES + 1)
        if len(page) > MAX_PAGE_BYTES:
            raise WebToolError('The page is too large to extract safely.')
        charset = response.headers.get_content_charset() or 'utf-8'
        source = page.decode(charset, errors='replace')
    except WebToolError:
        raise
    except (OSError, ssl.SSLError, http.client.HTTPException, LookupError, ValueError) as exc:
        raise WebToolError('Could not fetch or decode the requested public page.') from exc
    finally:
        if raw_socket:
            raw_socket.close()
        if 'connection' in locals() and connection is not raw_socket:
            connection.close()

    if content_type.startswith('text/plain'):
        title = parsed.hostname
        description = ''
        extracted = '\n'.join(line.strip() for line in source.splitlines() if line.strip())
    else:
        parser = _PageParser()
        parser.feed(source)
        title = ' '.join(parser.title).strip() or parsed.hostname
        description = parser.description
        extracted = re.sub(r'\n{3,}', '\n\n', re.sub(
            r' *\n *', '\n', re.sub(r'[ \t]+', ' ', ''.join(parser.text))
        )).strip()
    if not extracted:
        raise WebToolError('No readable page content was found.')
    return {
        'title': title,
        'url': url.strip(),
        'description': description,
        'content': extracted[:MAX_PAGE_CHARS],
        'content_chars': len(extracted),
        'truncated': len(extracted) > MAX_PAGE_CHARS,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'content_type': content_type.split(';', 1)[0],
    }
