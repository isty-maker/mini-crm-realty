import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import update_code_index as uci


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(uci.time, "sleep", lambda *_args, **_kwargs: None)


def _build_http_error(url: str, code: int) -> HTTPError:
    return HTTPError(url, code, "error", hdrs=None, fp=None)


def test_validate_url_head_405_then_get_200(monkeypatch):
    url = uci.BASE_RAW_URL + "README.md"

    def fake_send_request(request_url: str, *, method: str, timeout: float, headers):
        if method == "HEAD":
            raise _build_http_error(request_url, 405)
        if method == "GET":
            return 200
        raise AssertionError("unexpected method")

    monkeypatch.setattr(uci, "_send_request", fake_send_request)

    result = uci.validate_url(url)
    assert result.state == uci.ValidationState.VALID
    assert "HEAD 405" in result.detail
    assert "GET 200" in result.detail


def test_validate_url_head_403_then_get_403_skipped(monkeypatch):
    url = uci.BASE_RAW_URL + "README.md"

    def fake_send_request(request_url: str, *, method: str, timeout: float, headers):
        if method == "HEAD":
            raise _build_http_error(request_url, 403)
        if method == "GET":
            raise _build_http_error(request_url, 403)
        raise AssertionError("unexpected method")

    monkeypatch.setattr(uci, "_send_request", fake_send_request)

    summary = uci.validate_links([url])
    assert summary.error_count == 0
    assert summary.skipped_count == 1
    skipped = summary.skipped[0]
    assert skipped.state == uci.ValidationState.SKIPPED
    assert "HEAD 403" in skipped.detail
    assert "GET 403" in skipped.detail


def test_validate_url_get_404_is_error(monkeypatch):
    url = uci.BASE_RAW_URL + "README.md"

    def fake_send_request(request_url: str, *, method: str, timeout: float, headers):
        if method == "HEAD":
            raise _build_http_error(request_url, 405)
        if method == "GET":
            raise _build_http_error(request_url, 404)
        raise AssertionError("unexpected method")

    monkeypatch.setattr(uci, "_send_request", fake_send_request)

    summary = uci.validate_links([url])
    assert summary.error_count == 1
    error = summary.errors[0]
    assert error.state == uci.ValidationState.ERROR
    assert "GET 404" in error.detail


def test_validate_url_malformed_pattern():
    result = uci.validate_url("https://example.com/bad-link.txt")
    assert result.state == uci.ValidationState.ERROR
    assert "malformed" in result.detail
