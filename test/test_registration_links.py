from socials.bluesky import _build_registration_facets
from utils.registration_links import resolve_registration_gallery_url


def test_resolve_registration_gallery_url_defaults_to_jetphotos():
    assert resolve_registration_gallery_url("ec-xyz") == "https://www.jetphotos.com/registration/EC-XYZ"


def test_resolve_registration_gallery_url_for_planespotters():
    assert resolve_registration_gallery_url("ec-xyz", provider="planespotters") == "https://www.planespotters.net/registration/EC-XYZ"


def test_resolve_registration_gallery_url_invalid_registration_returns_none():
    assert resolve_registration_gallery_url("") is None


def test_bluesky_registration_facet_uses_utf8_byte_offsets():
    text = "Vuelo Ñ Test EC-TST 😊"
    registration = "EC-TST"
    registration_url = "https://example.com/registration/EC-TST"

    facets = _build_registration_facets(text, registration, registration_url)

    assert facets == [
        {
            "index": {
                "byteStart": 14,
                "byteEnd": 20,
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": registration_url,
                }
            ],
        }
    ]
