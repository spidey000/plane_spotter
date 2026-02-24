import pytest

from socials import telegram as tg


def test_parse_registration_reason_pairs_parses_multiple_entries():
    payload = " (ec-lmd, Primera visita) (N12345, VIP guest) "
    pairs = tg._parse_registration_reason_pairs(payload)

    assert pairs == [
        ("EC-LMD", "Primera visita"),
        ("N12345", "VIP guest"),
    ]


def test_parse_registration_reason_pairs_accepts_commas_between_groups():
    payload = "(EC-AAA, Demo 1),(EC-BBB, Otra razon)"
    pairs = tg._parse_registration_reason_pairs(payload)

    assert pairs == [
        ("EC-AAA", "Demo 1"),
        ("EC-BBB", "Otra razon"),
    ]


def test_parse_registration_reason_pairs_rejects_invalid_pairs():
    with pytest.raises(ValueError):
        tg._parse_registration_reason_pairs("(EC-XYZ)")
