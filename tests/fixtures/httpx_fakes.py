"""Fakes for httpx.stream/httpx.get that reproduce the exact behavior verified empirically
against this environment's proxy (docs/DECISIONS.md D3): a policy-blocked host raises
httpx.ProxyError directly from the call, not from inside the context manager or as an HTTP
response status."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class FakeStreamResponse:
    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self._content = content

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def iter_bytes(self):
        yield self._content

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]


def make_fake_stream(
    *, status_code: int = 200, content: bytes = b"", raise_exc: Exception | None = None
):
    def fake_stream(method: str, url: str, **kwargs: Any):
        if raise_exc is not None:
            raise raise_exc
        return FakeStreamResponse(status_code, content)

    return fake_stream


@dataclass
class FakeGetResponse:
    status_code: int = 200
    _json: Any = None
    content: bytes = b"{}"

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]


def make_fake_get(
    *, status_code: int = 200, json_body: Any = None, raise_exc: Exception | None = None
):
    def fake_get(url: str, **kwargs: Any):
        if raise_exc is not None:
            raise raise_exc
        import json as _json

        return FakeGetResponse(status_code, json_body, _json.dumps(json_body or {}).encode())

    return fake_get
