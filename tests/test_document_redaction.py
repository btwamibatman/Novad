from app.services.document_redaction import (
    TextCandidate,
    _resolve_text_overlaps,
    classify_kz_identifier,
    find_text_candidates,
    validate_kz_identifier,
)


def _valid_identifier(first_eleven: str) -> str:
    assert len(first_eleven) == 11
    for checksum in range(10):
        candidate = f"{first_eleven}{checksum}"
        if validate_kz_identifier(candidate):
            return candidate
    raise AssertionError("Unable to create a valid synthetic identifier")


def test_person_requires_context_and_avoids_capitalized_document_phrases():
    text = (
        "Республика Казахстан\n"
        "Северный Казахстан\n"
        "Общие Положения\n"
        "Акционерное Общество\n"
        "ФИО: Иванов Иван Иванович\n"
        "Азамат: Әлиев Нұрлан Серікұлы"
    )

    findings = find_text_candidates(text, {"personal"})

    assert [item.text for item in findings if item.category == "PERSON"] == [
        "Иванов Иван Иванович",
        "Әлиев Нұрлан Серікұлы",
    ]


def test_person_does_not_treat_form_column_headers_as_a_name():
    text = "Фамилия Имя Отчество Категория Заявителя\nЛауазымы Азаматтарды қабылдау күні"

    assert not [item for item in find_text_candidates(text, {"personal"}) if item.category == "PERSON"]


def test_address_keeps_the_complete_comma_separated_value():
    text = "Адрес: г. Алматы, ул. Абая, д. 15, кв. 3\nТелефон: +7 700 111 22 33"

    findings = find_text_candidates(text, {"personal"})

    addresses = [item.text for item in findings if item.category == "ADDRESS"]
    assert addresses == ["г. Алматы, ул. Абая, д. 15, кв. 3"]


def test_unlabelled_kazakh_address_includes_city_street_and_building():
    text = "Астана қ., Есіл ауданы, Мәңгілік Ел даңғылы, 8, офис 4"

    findings = find_text_candidates(text, {"personal"})

    addresses = [item.text for item in findings if item.category == "ADDRESS"]
    assert addresses == [text]


def test_address_stops_before_the_next_organization_field():
    text = "г. Семей, ул. Абая, д. 8, ГУ «Аппарат маслихата области»"

    findings = find_text_candidates(text, {"personal", "service"})

    assert [(item.category, item.text) for item in findings] == [
        ("ADDRESS", "г. Семей, ул. Абая, д. 8"),
        ("ORG", "ГУ «Аппарат маслихата области»"),
    ]


def test_bare_identifiers_require_checksum_and_use_current_bin_structure():
    synthetic_iin = _valid_identifier("90010130000")
    synthetic_bin = _valid_identifier("24014000000")
    invalid = synthetic_iin[:-1] + str((int(synthetic_iin[-1]) + 1) % 10)

    assert classify_kz_identifier(synthetic_iin) == "IIN"
    assert classify_kz_identifier(synthetic_bin) == "BIN"
    assert classify_kz_identifier(invalid) is None

    personal = find_text_candidates(f"Заявитель {synthetic_iin}; код {invalid}", {"personal"})
    service = find_text_candidates(f"Компания {synthetic_bin}; код {invalid}", {"service"})

    assert [(item.category, item.text) for item in personal] == [("IIN", synthetic_iin)]
    assert [(item.category, item.text) for item in service] == [("BIN", synthetic_bin)]


def test_bare_identifier_does_not_consume_cadastral_or_spaced_numbers():
    text = "Кадастровый номер 21-320-109-1207, значение 292 266 237 221"

    assert not [
        item
        for item in find_text_candidates(text, {"personal", "service"})
        if item.category in {"IIN", "BIN", "IIN_OR_BIN"}
    ]


def test_explicit_identifier_label_is_kept_even_when_ocr_breaks_checksum():
    findings = find_text_candidates("ИИН: 123456789012", {"personal"})

    assert [(item.category, item.text, item.confidence) for item in findings] == [
        ("IIN", "123456789012", 0.86)
    ]


def test_service_terms_cover_ru_and_kk_forms_without_masking_generic_nouns():
    text = (
        "ТОО «Альфа»\n"
        "ЖШС «Бета»\n"
        "Алматы қаласының әкімдігі\n"
        "Акимат города Астаны\n"
        "Прокуратура проверила материалы, суд рассмотрел дело, нотариус выдал документ."
    )

    findings = find_text_candidates(text, {"service"})
    organizations = [item.text for item in findings if item.category == "ORG"]

    assert organizations == [
        "ТОО «Альфа»",
        "ЖШС «Бета»",
        "Алматы қаласының әкімдігі",
        "Акимат города Астаны",
    ]


def test_kazakh_common_word_and_document_words_are_not_service_entities():
    text = "ақ өңірлік даму, активность выросла, счет собственных средств"

    findings = find_text_candidates(text, {"service"})

    assert not [item for item in findings if item.category in {"ORG", "DOC_ID"}]


def test_email_label_does_not_duplicate_email_as_a_postal_address():
    findings = find_text_candidates("Электронный адрес: user@example.com", {"personal"})

    assert [(item.category, item.text) for item in findings] == [("EMAIL", "user@example.com")]


def test_overlap_resolution_reserves_range_for_higher_priority_entity():
    candidates = [
        TextCandidate("personal", "PERSON", "города Алматы", 7, 21, 0.88, 60),
        TextCandidate("service", "ORG", "Акимат города Алматы", 0, 21, 0.86, 70),
    ]

    assert _resolve_text_overlaps(candidates) == [candidates[1]]
