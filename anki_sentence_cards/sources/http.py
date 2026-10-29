"""Single HTTP client for all external sources (stdlib only).

The only exception that leaves this module is SourceError, with a short
human-readable message that is safe to show in the user's report.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

MAX_TIMEOUT = 10.0
RETRIES = 2  # extra attempts after the first: 3 in total
PAUSE = 0.5
USER_AGENT = "Mozilla/5.0 anki-sentence-cards"
PER_HOST = 2  # the break fetches words in parallel; one host must not be flooded

_host_lock = threading.Lock()
_host_gates = {}


def _gate(url: str):
    """Semaphore of this URL's host, shared by every thread of the add-on."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    with _host_lock:
        gate = _host_gates.get(host)
        if gate is None:
            gate = _host_gates[host] = threading.Semaphore(PER_HOST)
    return gate


class SourceError(Exception):
    """A source failed; str(e) is a short message for the user."""


def _urlopen(req, timeout):  # the only function that touches the network
    return urllib.request.urlopen(req, timeout=timeout)


def _sleep(seconds):
    time.sleep(seconds)


def _fetch(url: str, params: Optional[dict], data: Optional[dict],
           headers: Optional[dict], timeout: float) -> bytes:
    timeout = min(float(timeout), MAX_TIMEOUT)
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    last = "сбой сети"
    gate = _gate(url)
    for attempt in range(RETRIES + 1):
        if attempt:
            _sleep(PAUSE * attempt)
        try:
            req = urllib.request.Request(url, data=body, headers=hdrs)
            with gate:
                with _urlopen(req, timeout) as resp:
                    return resp.read()
        except urllib.error.HTTPError as e:
            e.close()
            last = "сервис ответил ошибкой %d" % e.code
            if e.code < 500:  # client errors will not fix themselves
                break
        except (TimeoutError, socket.timeout):
            last = "сервис не ответил за %d с" % timeout
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)):
                last = "сервис не ответил за %d с" % timeout
            else:
                last = "нет соединения с сервисом"
        except ValueError:
            raise SourceError("некорректный адрес сервиса")
        except Exception:  # OSError, ssl, http.client errors: never leak raw
            last = "сбой сети"
    raise SourceError(last)


def _decode(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise SourceError("сервис вернул непонятный ответ")


def get_json(url: str, params: Optional[dict] = None, timeout: float = 10.0,
             headers: Optional[dict] = None) -> Any:
    return _decode(_fetch(url, params, None, headers, timeout))


def post_form(url: str, data: dict, timeout: float = 10.0,
              headers: Optional[dict] = None) -> Any:
    return _decode(_fetch(url, None, data, headers, timeout))


def get_bytes(url: str, params: Optional[dict] = None, timeout: float = 10.0) -> bytes:
    return _fetch(url, params, None, None, timeout)
