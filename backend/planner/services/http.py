"""Shared HTTP session for the third-party APIs."""
import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# One pooled session keeps TLS connections alive between calls. Connection
# drops and 5xx blips are retried once; read timeouts are not, so a slow
# server costs one timeout rather than several.
session = requests.Session()
_adapter = HTTPAdapter(
    pool_maxsize=16,
    max_retries=Retry(
        total=1, connect=1, read=0, status=1, backoff_factor=0.2,
        status_forcelist=(502, 503, 504), allowed_methods=("GET",),
    ),
)
session.mount("https://", _adapter)
session.mount("http://", _adapter)


def get_json(url, params=None):
    """GET a URL and return (status_code, parsed JSON). Raises requests errors."""
    response = session.get(
        url,
        params=params,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        timeout=(settings.HTTP_CONNECT_TIMEOUT, settings.HTTP_READ_TIMEOUT),
    )
    return response.status_code, response.json()
