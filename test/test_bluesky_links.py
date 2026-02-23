from socials import bluesky


def test_inject_fr24_hyperlink_replaces_url_with_label() -> None:
    original = "FR24: https://example.com\nNext line"
    new_text, facet = bluesky._inject_fr24_hyperlink(original, "https://example.com")

    assert "FlightRadar24" in new_text
    assert "https://example.com" not in new_text
    assert facet is not None
    assert facet["features"][0]["uri"] == "https://example.com"


def test_inject_fr24_hyperlink_noop_without_url() -> None:
    original = "FR24: https://example.com"
    new_text, facet = bluesky._inject_fr24_hyperlink(original, None)

    assert new_text == original
    assert facet is None
