"""Solr indexing and search tuning (IPackageController hooks)."""

import json

import pytest

from ckanext.cioos.logic import _build_spatial_params
from ckanext.cioos.plugin import CioosPlugin


@pytest.fixture
def plugin():
    return CioosPlugin()


def _dataset(**fields):
    data = {"id": "abc", "name": "a-dataset", "type": "dataset"}
    data.update(fields)
    return data


class TestBeforeDatasetIndex:
    def test_non_dataset_types_are_untouched(self, plugin):
        data = {"type": "harvest", "keywords": '{"en": ["x"]}'}
        assert plugin.before_dataset_index(dict(data)) == data

    def test_splits_bilingual_fields(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(
                keywords=json.dumps({"en": ["ocean", "salinity"], "fr": ["océan"]}),
                title_translated=json.dumps({"en": "Title", "fr": "Titre"}),
                notes_translated=json.dumps({"en": "Notes", "fr": "Résumé"}),
                citation=json.dumps({"en": "cite en", "fr": "cite fr"}),
            )
        )
        assert out["tags_en"] == ["ocean", "salinity"]
        assert out["tags_fr"] == ["océan"]
        assert out["tags"] == ["ocean", "salinity", "océan"]
        assert (out["title_en"], out["title_fr"]) == ("Title", "Titre")
        assert (out["notes_en"], out["notes_fr"]) == ("Notes", "Résumé")
        assert (out["citation_en"], out["citation_fr"]) == ("cite en", "cite fr")

    def test_temporal_extent_range(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(
                **{"temporal-extent": '{"begin": "2020-01-01", "end": "2021-06-30"}'}
            )
        )
        assert out["temporal-extent-begin"] == "2020-01-01"
        assert out["temporal-extent-end"] == "2021-06-30"
        assert out["temporal-extent-range"] == "[2020-01-01 TO 2021-06-30]"

    def test_open_ended_temporal_extent(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(**{"temporal-extent": '{"begin": "2020-01-01"}'})
        )
        assert out["temporal-extent-range"] == "[2020-01-01 TO *]"

    def test_flattened_temporal_extent_fallback(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(**{"temporal-extent-begin": "2019-01-01", "temporal-extent": ""})
        )
        assert out["temporal-extent-range"] == "[2019-01-01 TO *]"

    def test_vertical_extent_and_json_lists(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(
                **{
                    "vertical-extent": '{"min": "0", "max": "100"}',
                    "eov": '["seaSurfaceTemperature"]',
                    "ecv": '["oceanColour"]',
                    "projects": '["Project A"]',
                }
            )
        )
        assert (out["vertical-extent-min"], out["vertical-extent-max"]) == ("0", "100")
        assert out["eov"] == ["seaSurfaceTemperature"]
        assert out["ecv"] == ["oceanColour"]
        assert out["projects"] == ["Project A"]

    def test_resource_translated_fields(self, plugin):
        out = plugin.before_dataset_index(
            _dataset(
                resources=[
                    {
                        "name": '{"en": "Data", "fr": "Données"}',
                        "description": '{"en": "d", "fr": "d fr"}',
                    }
                ]
            )
        )
        res = out["resources"][0]
        assert res["name_translated"] == {"en": "Data", "fr": "Données"}
        assert res["description_translated"] == {"en": "d", "fr": "d fr"}

    @pytest.mark.xfail(
        strict=True,
        reason="Known bug kept by the behaviour-preserving extraction: "
        "lxml's strip_tags() returns None, so harvest_document_content_en/_fr "
        "are always indexed as None.",
    )
    def test_harvest_document_split_by_language(self, plugin):
        xml = """<mdb:MD_Metadata
            xmlns:mdb="http://standards.iso.org/iso/19115/-3/mdb/2.0"
            xmlns:lan="http://standards.iso.org/iso/19115/-3/lan/1.0">
          <mdb:defaultLocale><lan:PT_Locale><lan:language>
            <lan:LanguageCode codeListValue="eng"/>
          </lan:language></lan:PT_Locale></mdb:defaultLocale>
          <title>English title<lan:LocalisedCharacterString locale="#fr">Titre français</lan:LocalisedCharacterString></title>
        </mdb:MD_Metadata>"""
        out = plugin.before_dataset_index(_dataset(harvest_document_content=xml))
        assert "English title" in out["harvest_document_content_en"]
        assert "Titre français" not in out["harvest_document_content_en"]
        assert "Titre français" in out["harvest_document_content_fr"]


class TestBeforeDatasetSearch:
    def test_temporal_range_filter(self, plugin):
        params = plugin.before_dataset_search(
            {"extras": {"ext_year_begin": "2000", "ext_year_end": "2010"}}
        )
        assert params["fq_list"] == ["+temporal-extent-range:[2000 TO 2010]"]

    def test_temporal_range_filter_including_empty(self, plugin):
        params = plugin.before_dataset_search(
            {"extras": {"ext_year_begin": "2000", "ext_show_empty_range": "true"}}
        )
        assert params["fq_list"] == [
            "+(temporal-extent-range:[2000 TO *] OR (*:* NOT temporal-extent-range:[* TO *]))"
        ]

    def test_metadata_date_filters(self, plugin):
        params = plugin.before_dataset_search(
            {
                "extras": {
                    "ext_created_begin": "2024-01-01",
                    "ext_modified_end": "2024-12-31",
                }
            }
        )
        assert params["fq_list"] == [
            "+metadata_created:[2024-01-01T00:00:00Z TO *]",
            "+metadata_modified:[* TO 2024-12-31T23:59:59Z]",
        ]

    def test_no_filters(self, plugin):
        assert plugin.before_dataset_search({})["fq_list"] == []


class TestGroupContacts:
    def test_merges_entries_for_the_same_person(self, plugin):
        out = plugin.group_by_ind_or_org(
            [
                {
                    "individual-name": "A",
                    "organisation-name": "Org",
                    "role": "custodian",
                },
                {"individual-name": "A", "organisation-name": "Org", "role": "author"},
                {"individual-name": "B", "organisation-name": "Org", "role": "author"},
            ]
        )
        assert out == [
            {
                "individual-name": "A",
                "organisation-name": "Org",
                "role": ["custodian", "author"],
            },
            {"individual-name": "B", "organisation-name": "Org", "role": "author"},
        ]


class TestSpatialParams:
    def test_bbox(self):
        assert _build_spatial_params({"bbox": "-130,45,-120,55"}) == {
            "extras": {"ext_bbox": "-130.0,45.0,-120.0,55.0"}
        }

    def test_box_poly(self):
        assert _build_spatial_params({"poly": "BOX(-130,45,-120,55)"}) == {
            "extras": {"ext_bbox": "-130.0,45.0,-120.0,55.0"}
        }

    def test_polygon(self):
        params = _build_spatial_params(
            {"poly": "POLYGON((-130 45,-120 45,-120 55,-130 55,-130 45))"}
        )
        assert params["fq"].startswith("{!field f=spatial_geom}Intersects(POLYGON")

    def test_invalid(self):
        assert _build_spatial_params({"poly": "not wkt"}) is None
        assert _build_spatial_params({}) is None
