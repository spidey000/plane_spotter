from __future__ import annotations

from dataclasses import dataclass

import utils.image_finder as image_finder


@dataclass
class FakeResponse:
    status_code: int
    text: str
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}


class FakeScraper:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("Unexpected extra request")
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _patch_image_finder_config(monkeypatch, **overrides):
    config = {
        "enabled": True,
        "providers": ["jetphotos", "planespotters"],
        "request_timeout_seconds": 5,
        "max_retries": 3,
        "base_delay_seconds": 0,
        "max_delay_seconds": 0,
        "jitter_seconds": 0,
        "positive_cache_ttl_seconds": 3600,
        "negative_cache_ttl_seconds": 60,
        "provider_cooldown_seconds": 120,
        "user_agent": "test-agent",
    }
    config.update(overrides)

    def fake_get_config(key: str):
        if key == "image_finder":
            return config
        return None

    monkeypatch.setattr(image_finder.cfg, "get_config", fake_get_config)


def _patch_runtime(monkeypatch) -> None:
    image_finder.clear_image_finder_runtime_state()
    monkeypatch.setattr(image_finder.time, "sleep", lambda _: None)
    monkeypatch.setattr(image_finder, "record_api_event", lambda **_: None)


def test_jp_retries_429_then_returns_full_size(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    scraper = FakeScraper(
        [
            FakeResponse(status_code=429, text="", headers={"Retry-After": "0"}),
            FakeResponse(
                status_code=200,
                text='<img class="result__photo" src="//cdn.jetphotos.com/400/1/example.jpg"/>',
            ),
        ]
    )
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    url = image_finder.get_first_image_url_jp(" ec-abc ")

    assert url == "https://cdn.jetphotos.com/full/1/example.jpg"
    assert len(scraper.calls) == 2
    assert scraper.calls[0]["params"]["keywords"] == "EC-ABC"
    assert scraper.calls[0]["headers"] is None
    assert scraper.calls[1]["headers"] is None


def test_planespotters_uses_largest_srcset_candidate(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    scraper = FakeScraper(
        [
            FakeResponse(
                status_code=200,
                text=(
                    '<img class="photo_card__photo" '
                    'srcset="//t.plnspttrs.net/x_280.jpg 280w, //t.plnspttrs.net/x_640.jpg 640w"/>'
                ),
            )
        ]
    )
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    url = image_finder.get_first_image_url_pp("EC-TEST")

    assert url == "https://t.plnspttrs.net/x_640.jpg"
    assert len(scraper.calls) == 1


def test_jetphotos_prefers_image_matching_registration(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    scraper = FakeScraper(
        [
            FakeResponse(
                status_code=200,
                text=(
                    '<img class="result__photo" src="//cdn.jetphotos.com/400/1/not-target.jpg" '
                    'alt="N123AB - Boeing 737"/>'
                    '<img class="result__photo" src="//cdn.jetphotos.com/400/2/target.jpg" '
                    'alt="EC-MLP - Airbus A330-202 - Iberia"/>'
                ),
            )
        ]
    )
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    url = image_finder.get_first_image_url_jp("EC-MLP")

    assert url == "https://cdn.jetphotos.com/full/2/target.jpg"


def test_planespotters_prefers_matching_registration_from_photo_links(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    scraper = FakeScraper(
        [
            FakeResponse(
                status_code=200,
                text=(
                    '<a href="/photo/1/not-target">'
                    '<img class="mx-auto w-full transition duration-200 hover:scale-102" '
                    'src="https://t.plnspttrs.net/11111/not_target_280.jpg" alt="N123AB Boeing 737"/>'
                    "</a>"
                    '<a href="/photo/2/ec-mlp">'
                    '<img class="mx-auto w-full transition duration-200 hover:scale-102" '
                    'src="https://t.plnspttrs.net/22222/target_280.jpg" alt="EC-MLP Iberia Airbus A330-202"/>'
                    "</a>"
                ),
            )
        ]
    )
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    url = image_finder.get_first_image_url_pp("EC-MLP")

    assert url == "https://t.plnspttrs.net/22222/target_280.jpg"


def test_provider_cooldown_skips_second_request(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch, negative_cache_ttl_seconds=0, max_retries=1)

    scraper = FakeScraper([FakeResponse(status_code=403, text="Forbidden")])
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    first = image_finder.get_first_image_url_jp("EC-ONE")
    second = image_finder.get_first_image_url_jp("EC-TWO")

    assert first is None
    assert second is None
    assert len(scraper.calls) == 1


def test_positive_cache_avoids_second_network_call(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    scraper = FakeScraper(
        [
            FakeResponse(
                status_code=200,
                text='<img class="result__photo" src="//cdn.jetphotos.com/400/2/cache.jpg"/>',
            )
        ]
    )
    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", lambda: scraper)

    first = image_finder.get_first_image_url_jp("EC-CACHE")
    second = image_finder.get_first_image_url_jp("EC-CACHE")

    assert first == "https://cdn.jetphotos.com/full/2/cache.jpg"
    assert second == first
    assert len(scraper.calls) == 1


def test_nullish_registration_returns_none_without_requests(monkeypatch) -> None:
    _patch_runtime(monkeypatch)
    _patch_image_finder_config(monkeypatch)

    def fail_create_scraper():
        raise AssertionError("create_scraper should not be called for nullish registrations")

    monkeypatch.setattr(image_finder.cloudscraper, "create_scraper", fail_create_scraper)

    assert image_finder.get_first_image_url_jp(None) is None
    assert image_finder.get_first_image_url_pp("null") is None
    assert image_finder.get_first_image_url("  ") is None
