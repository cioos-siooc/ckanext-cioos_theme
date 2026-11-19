"""Tests for util/collections.py: collection links read from aggregation-info."""

import json
import logging

from ckanext.cioos_theme.util.collections import extract_collections, find_collection

UUID = "b30289fc-fcbd-4624-a44b-eb3a703c4e32"
OTHER_UUID = "c96eb674-ff35-4b1d-b6c2-0356b99f530a"
CID = "ca-cioos_" + UUID
OTHER_CID = "ca-cioos_" + OTHER_UUID
NAME = {"en": "Bedford Basin Collection", "fr": "Collection du bassin de Bedford"}
DOI = "10.60622/v6nn-kw50"


def entry(code, name=NAME, initiative="collection"):
    return {
        "aggregate-dataset-name": name,
        "aggregate-dataset-identifier_code": code,
        "association-type": "largerWorkCitation",
        "initiative-type": initiative,
    }


def test_catalogue_url():
    url = "https://catalogue.cioosatlantic.ca/dataset/ca-cioos_" + UUID
    assert extract_collections([entry(url)]) == [(CID, NAME)]


def test_prefixed_uuid_is_kept():
    assert extract_collections([entry("ca-cioos_" + UUID)]) == [(CID, NAME)]


def test_guid_dot_becomes_hyphen():
    assert extract_collections([entry("ca.cioos_" + UUID)]) == [(CID, NAME)]


def test_other_authority_keeps_its_prefix():
    url = "https://catalogue.cioosatlantic.ca/dataset/ca-gc-dfo-mpo-cnodc-cndoc_" + UUID
    expected = "ca-gc-dfo-mpo-cnodc-cndoc_" + UUID
    assert extract_collections([entry(url)]) == [(expected, NAME)]
    guid = "ca.gc.dfo-mpo.cnodc-cndoc_" + UUID
    assert find_collection(guid) == (UUID, expected)


def test_bare_uuid_assumes_cioos_prefix():
    assert extract_collections([entry(UUID)]) == [(CID, NAME)]
    assert find_collection("urn:uuid:" + UUID) == (UUID, CID)


def test_upper_case_is_lower_cased():
    assert extract_collections([entry("CA.CIOOS_" + UUID.upper())]) == [(CID, NAME)]


def test_doi_link_is_stored_as_bare_doi():
    assert extract_collections([entry("https://doi.org/" + DOI)]) == [(DOI, NAME)]


def test_doi_forms_give_the_same_id():
    for link in (DOI, "doi:" + DOI, "https://dx.doi.org/" + DOI, "DOI:10.60622/V6NN-KW50"):
        assert find_collection(link) == (DOI, DOI), link


def test_doi_is_checked_before_uuid():
    doi_with_uuid = "10.5285/3a1e1bde-f356-c7f5-e063-7086abc04c0b"
    assert find_collection("doi:" + doi_with_uuid) == (doi_with_uuid, doi_with_uuid)


def test_same_doi_in_different_forms_counts_once():
    entries = [entry("https://doi.org/" + DOI), entry("doi:" + DOI)]
    assert extract_collections(entries) == [(DOI, NAME)]


def test_doi_and_uuid_links_give_two_ids_with_the_same_title():
    entries = [entry("https://doi.org/" + DOI), entry(UUID)]
    assert extract_collections(entries) == [(DOI, NAME), (CID, NAME)]


def test_link_without_doi_or_uuid_is_skipped_and_logged(caplog):
    link = "https://data.ceotr.ca/erddap/tabledap/new_bb1_hyp_level2_binned.html"
    with caplog.at_level(logging.WARNING):
        result = extract_collections([entry(link)], "ca-cioos_" + OTHER_UUID)
    assert result == []
    assert "new_bb1_hyp_level2_binned" in caplog.text


def test_other_initiative_types_are_ignored():
    entries = [entry(UUID, initiative="project"), entry(OTHER_UUID, initiative="")]
    assert extract_collections(entries) == []


def test_json_string_input():
    assert extract_collections(json.dumps([entry(UUID)])) == [(CID, NAME)]


def test_name_as_json_string():
    result = extract_collections([entry(UUID, name=json.dumps(NAME))])
    assert result == [(CID, NAME)]


def test_missing_french_name_falls_back_to_english():
    result = extract_collections([entry(UUID, name={"en": "Bedford", "fr": ""})])
    assert result == [(CID, {"en": "Bedford", "fr": "Bedford"})]


def test_missing_english_name_falls_back_to_french():
    result = extract_collections([entry(UUID, name={"fr": "Bedford FR"})])
    assert result == [(CID, {"en": "Bedford FR", "fr": "Bedford FR"})]


def test_missing_title_falls_back_to_collection_uuid():
    result = extract_collections([entry(UUID, name={"en": "", "fr": ""})])
    assert result == [(CID, {"en": CID, "fr": CID})]


def test_self_reference_is_skipped():
    url = "https://catalogue.cioosatlantic.ca/dataset/ca-cioos_" + UUID
    assert extract_collections([entry(url)], "ca-cioos_" + UUID) == []


def test_same_collection_in_different_forms_counts_once():
    url = "https://catalogue.cioosatlantic.ca/dataset/ca-cioos_" + UUID
    entries = [entry(url), entry("ca.cioos_" + UUID), entry(UUID), entry(OTHER_UUID)]
    assert extract_collections(entries) == [(CID, NAME), (OTHER_CID, NAME)]


def test_empty_inputs():
    assert extract_collections(None) == []
    assert extract_collections([]) == []
    assert extract_collections("") == []
    assert extract_collections("not json") == []
    assert find_collection(None) == (None, None)
