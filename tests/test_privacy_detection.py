import pytest

from app.services import privacy_detection
from app.services.privacy_detection import (
    PRIVACY_ENGINE_VERSION,
    PrivacyDetectionUnavailable,
    PrivacyEngine,
    validate_kz_iban,
    validate_luhn,
)
from app.services.documents.redaction import validate_kz_identifier


def _valid_identifier(first_eleven: str) -> str:
    for checksum in range(10):
        candidate = f"{first_eleven}{checksum}"
        if validate_kz_identifier(candidate):
            return candidate
    raise AssertionError("Unable to create a valid synthetic identifier")


def test_presidio_engine_uses_one_taxonomy_for_kz_identifiers_and_contacts():
    iin = _valid_identifier("90010130000")
    bin_value = _valid_identifier("24014000000")
    engine = PrivacyEngine(languages=[])

    result = engine.detect_text(
        f"Заявитель {iin}, БИН: {bin_value}, email user@example.kz",
        {"personal", "service"},
        include_ner=False,
    )

    assert result.complete is True
    assert result.detectors == ["presidio"]
    assert {(span.category, span.text) for span in result.spans} == {
        ("IIN", iin),
        ("BIN", bin_value),
        ("EMAIL", "user@example.kz"),
    }
    assert all(span.source.startswith("presidio-") for span in result.spans)
    assert PRIVACY_ENGINE_VERSION == "presidio-local-v1"


def test_kz_financial_recognizers_validate_iban_card_and_currency_symbol():
    assert validate_kz_iban("KZ86125KZT5004100100") is True
    assert validate_kz_iban("KZ00125KZT5004100100") is False
    assert validate_luhn("4111 1111 1111 1111") is True

    result = PrivacyEngine(languages=[]).detect_text(
        "Счёт KZ86125KZT5004100100, карта 4111 1111 1111 1111, сумма 5 000 ₸.",
        {"financial"},
        include_ner=False,
    )

    assert [(span.category, span.text) for span in result.spans] == [
        ("IBAN", "KZ86125KZT5004100100"),
        ("PAYMENT_CARD", "4111 1111 1111 1111"),
        ("AMOUNT", "5 000 ₸"),
    ]


def test_detector_failures_are_reported_and_fail_closed_when_requested(monkeypatch):
    def unavailable(language, model_dir):
        raise PrivacyDetectionUnavailable("model missing")

    monkeypatch.setattr(privacy_detection, "_stanza_pipeline", unavailable)
    engine = PrivacyEngine(languages=["kk"])

    result = engine.detect_text(
        "email user@example.kz",
        {"personal"},
        include_ner=True,
        fail_closed=False,
    )

    assert [(failure.detector, failure.language) for failure in result.failures] == [
        ("stanza", "kk")
    ]
    assert result.complete is False

    with pytest.raises(PrivacyDetectionUnavailable, match="incomplete"):
        engine.detect_text(
            "email user@example.kz",
            {"personal"},
            include_ner=True,
            fail_closed=True,
        )
