"""Tests for util/collections.py: collection links read from aggregation-info."""

import json
import logging

from ckanext.cioos_theme.util.collections import extract_collections

UUID = "b30289fc-fcbd-4624-a44b-eb3a703c4e32"
OTHER_UUID = "c96eb674-ff35-4b1d-b6c2-0356b99f530a"
NAME = {"en": "Bedford Basin Collection", "fr": "Collection du bassin de Bedford"}


def entry(code, name=NAME, initiative="collection"):
    return {
        "aggregate-dataset-name": name,
        "aggregate-dataset-identifier_code": code,
        "association-type": "largerWorkCitation",
        "initiative-type": initiative,
    }


def test_bare_uuid():
    assert extract_collections([entry(UUID)]) == [(UUID, NAME)]


def test_catalogue_url_with_uuid():
    url = "https://catalogue.cioosatlantic.ca/dataset/ca-cioos_" + UUID
    assert extract_collections([entry(url)]) == [(UUID, NAME)]


def test_dataset_name_with_prefix():
    assert extract_collections([entry("ca-cioos_" + UUID)]) == [(UUID, NAME)]


def test_uuid_is_lower_cased():
    assert extract_collections([entry(UUID.upper())]) == [(UUID, NAME)]


def test_doi_only_is_skipped_and_logged(caplog):
    with caplog.at_level(logging.WARNING):
        result = extract_collections(
            [entry("https://doi.org/10.60622/v6nn-kw50")], "ca-cioos_" + OTHER_UUID
        )
    assert result == []
    assert "10.60622/v6nn-kw50" in caplog.text


def test_other_initiative_types_are_ignored():
    entries = [entry(UUID, initiative="project"), entry(OTHER_UUID, initiative="")]
    assert extract_collections(entries) == []


def test_json_string_input():
    assert extract_collections(json.dumps([entry(UUID)])) == [(UUID, NAME)]


def test_name_as_json_string():
    result = extract_collections([entry(UUID, name=json.dumps(NAME))])
    assert result == [(UUID, NAME)]


def test_missing_french_name_falls_back_to_english():
    result = extract_collections([entry(UUID, name={"en": "Bedford", "fr": ""})])
    assert result == [(UUID, {"en": "Bedford", "fr": "Bedford"})]


def test_missing_english_name_falls_back_to_french():
    result = extract_collections([entry(UUID, name={"fr": "Bedford FR"})])
    assert result == [(UUID, {"en": "Bedford FR", "fr": "Bedford FR"})]


def test_missing_name_falls_back_to_uuid():
    result = extract_collections([entry(UUID, name={"en": "", "fr": ""})])
    assert result == [(UUID, {"en": UUID, "fr": UUID})]


def test_self_reference_is_skipped():
    assert extract_collections([entry(UUID)], "ca-cioos_" + UUID) == []


def test_duplicate_links_are_deduplicated():
    entries = [entry(UUID), entry("ca-cioos_" + UUID), entry(OTHER_UUID)]
    assert extract_collections(entries) == [(UUID, NAME), (OTHER_UUID, NAME)]


def test_empty_inputs():
    assert extract_collections(None) == []
    assert extract_collections([]) == []
    assert extract_collections("") == []
    assert extract_collections("not json") == []
