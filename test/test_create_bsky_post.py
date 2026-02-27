from __future__ import annotations

import argparse

import requests

import utils.create_bsky_post as bsky_post


class DummyResponse:
    def __init__(self, status_code: int = 200, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self.text = text
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_fetch_embed_url_card_returns_none_on_blocked_url(monkeypatch):
    def fake_get(url, **kwargs):
        raise requests.HTTPError("HTTP 403")

    monkeypatch.setattr(bsky_post, "_tracked_get", fake_get)

    card = bsky_post.fetch_embed_url_card(
        pds_url="https://bsky.social",
        access_token="token",
        url="https://example.com/blocked",
    )

    assert card is None


def test_create_post_continues_when_embed_url_fetch_fails(monkeypatch):
    recorded_payload: dict = {}

    monkeypatch.setattr(
        bsky_post,
        "bsky_login_session",
        lambda *args, **kwargs: {"accessJwt": "jwt", "did": "did:plc:test"},
    )
    monkeypatch.setattr(bsky_post, "parse_facets", lambda *args, **kwargs: [])
    monkeypatch.setattr(bsky_post, "fetch_embed_url_card", lambda *args, **kwargs: None)

    def fake_post(url, **kwargs):
        recorded_payload.update(kwargs.get("json", {}))
        return DummyResponse(status_code=200)

    monkeypatch.setattr(bsky_post, "_tracked_post", fake_post)

    args = argparse.Namespace(
        pds_url="https://bsky.social",
        handle="handle",
        password="password",
        text="hello world",
        image=None,
        alt_text=None,
        lang=None,
        reply_to=None,
        embed_url="https://example.com/blocked",
        embed_ref=None,
        extra_facets=None,
    )

    bsky_post.create_post(args)

    record = recorded_payload["record"]
    assert record["text"] == "hello world"
    assert "embed" not in record


def test_fetch_embed_url_card_uses_browser_like_headers(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return DummyResponse(
            status_code=200,
            text='''<html><head>
<meta property="og:title" content="Demo title"/>
<meta property="og:description" content="Demo description"/>
<meta property="og:image" content="/demo.jpg"/>
</head></html>''',
            content=b"jpeg-bytes",
        )

    monkeypatch.setattr(bsky_post, "_tracked_get", fake_get)
    monkeypatch.setattr(bsky_post, "upload_file", lambda *args, **kwargs: {"$type": "blob"})

    card = bsky_post.fetch_embed_url_card(
        pds_url="https://bsky.social",
        access_token="token",
        url="https://example.com/path",
    )

    assert card is not None
    assert calls[0]["headers"]["User-Agent"]
    assert calls[0]["headers"]["Accept-Language"] == "en-US,en;q=0.9"
    assert calls[0]["timeout"] == 15
    assert calls[1]["url"] == "https://example.com/demo.jpg"
    assert calls[1]["headers"]["Referer"] == "https://example.com/path"
