"""
services/http_client.py — Resilient HTTP Infrastructure & Credential Sanitization
─────────────────────────────────────────────────────────────────────────────────
Enterprise-grade HTTP client layer for external service integrations:
  - Connection pooling with requests.Session and HTTPAdapter
  - Configurable exponential backoff retries on transient errors (429, 500, 502, 503, 504)
  - Separate connect and read timeouts to prevent thread starvation
  - Zero credential leakage in logs: automatic sanitization of query parameters and headers
  - Retry-After header parsing for compliant rate limit handling
"""

import re
import logging
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Standard timeout tuples: (connect_timeout_sec, read_timeout_sec)
# Connect timeout is set slightly larger than 3 to align with standard TCP packet retry windows.
DEFAULT_CONNECT_TIMEOUT = 3.05
DEFAULT_READ_TIMEOUT = 10.0
DEFAULT_TIMEOUT: Tuple[float, float] = (DEFAULT_CONNECT_TIMEOUT, DEFAULT_READ_TIMEOUT)

LLM_CONNECT_TIMEOUT = 3.05
LLM_READ_TIMEOUT = 30.0
LLM_TIMEOUT: Tuple[float, float] = (LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT)

SENSITIVE_PARAM_NAMES = {
    'app_id', 'api_key', 'apikey', 'key', 'secret',
    'token', 'access_token', 'password', 'auth'
}

_SHARED_SESSION: Optional[requests.Session] = None


def get_http_session(
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504),
    pool_connections: int = 10,
    pool_maxsize: int = 20,
) -> requests.Session:
    """Create or return a thread-safe requests.Session configured with resilient retries and connection pooling."""
    global _SHARED_SESSION
    if _SHARED_SESSION is not None:
        return _SHARED_SESSION

    session = requests.Session()

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        allowed_methods=frozenset(['GET', 'HEAD', 'OPTIONS']),
        raise_on_status=False,
        respect_retry_after_header=True,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    _SHARED_SESSION = session
    return _SHARED_SESSION


def sanitize_url(url: str) -> str:
    """Sanitize URL query string to ensure secrets like app_id or api_key are never leaked in logs."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url

        query_params = parse_qs(parsed.query, keep_blank_values=True)
        sanitized_params = {}
        for k, v_list in query_params.items():
            if k.lower() in SENSITIVE_PARAM_NAMES:
                sanitized_params[k] = ['[REDACTED]'] * len(v_list)
            else:
                sanitized_params[k] = v_list

        new_query = urlencode(sanitized_params, doseq=True)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
    except Exception:
        # Fallback regex masking in case urlparse fails
        return re.sub(r'([?&](?:app_id|api_key|key|token)=)[^&]+', r'\1[REDACTED]', url)


def sanitize_headers(headers: Optional[Dict]) -> Dict:
    """Return a copy of request/response headers with sensitive values masked."""
    if not headers:
        return {}
    sanitized = {}
    for k, v in headers.items():
        k_lower = str(k).lower()
        if k_lower in ('authorization', 'proxy-authorization', 'x-api-key', 'cookie'):
            sanitized[k] = '•••••••• (Masked)'
        else:
            sanitized[k] = v
    return sanitized


def parse_retry_after(response: Optional[requests.Response]) -> Optional[int]:
    """Extract integer wait seconds from the Retry-After header if present."""
    if response is None:
        return None

    retry_after = response.headers.get('Retry-After')
    if not retry_after:
        return None

    try:
        # Standard integer seconds format
        return max(1, int(retry_after))
    except (ValueError, TypeError):
        # In case of HTTP date format, provide a safe default backoff
        return 5
