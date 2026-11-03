"""Tests for the free-text search rewrite (plugin.py) and embeddings.py."""

import pytest
import requests

import ckanext.cioos_theme.embeddings as embeddings
from ckanext.cioos_theme.plugin import (
    FIELDED_QUERY_RE,
    OPERATOR_QUERY_RE,
    Cioos_ThemePlugin,
)


@pytest.fixture
def embed_calls(monkeypatch):
    """Stub the embeddings service; returns the list of texts it was asked for."""
    calls = []

    def fake_embed(text, timeout):
        calls.append(text)
        return [0.25, -0.5]

    monkeypatch.setattr(embeddings, "embed", fake_embed)
    return calls


def test_free_text_query_is_hybrid_when_a_vector_is_available(embed_calls):
    params = {"q": "whale sightings"}
    Cioos_ThemePlugin()._free_text_query(params, "whale sightings")

    assert embed_calls == ["whale sightings"]
    assert params["defType"] == "lucene"
    assert params["q"] == "{!bool should=$lexq should=$vecq}"
    # q.op=OR scoped to the lexical query, so CKAN's fq keeps its implicit AND
    assert params["lexq"] == "{!edismax q.op=OR}whale sightings"
    assert params["vecq"] == "{!knn f=embedding topK=20}[0.25, -0.5]"
    assert params["mm"] == "2<-1 5<80%"


def test_free_text_query_is_lexical_without_a_vector(monkeypatch):
    monkeypatch.setattr(embeddings, "embed", lambda text, timeout: None)
    params = {"q": "Placentia Bay: North Harbour"}
    Cioos_ThemePlugin()._free_text_query(params, "Placentia Bay: North Harbour")

    assert params["q"] == "{!edismax q.op=OR}Placentia Bay: North Harbour"
    assert "lexq" not in params and "vecq" not in params


@pytest.mark.parametrize(
    "q", ['"Prince Rupert"', "kelp -canopy", "temp*", "kelp OR eelgrass", "salinty~1"]
)
def test_search_syntax_stays_lexical(embed_calls, q):
    params = {"q": q}
    Cioos_ThemePlugin()._free_text_query(params, q)

    assert embed_calls == []
    assert params["q"] == "{!edismax q.op=OR}" + q


@pytest.mark.parametrize("q", ["id:abc", "tags:Oceans", "harvest_source_id:x AND y"])
def test_fielded_queries_are_detected(q):
    assert FIELDED_QUERY_RE.search(q)


@pytest.mark.parametrize("q", ["Placentia Bay: North Harbour", "sea surface temperature"])
def test_free_text_is_not_fielded(q):
    assert not FIELDED_QUERY_RE.search(q)
    assert not OPERATOR_QUERY_RE.search(q)


@pytest.fixture
def fresh_service(monkeypatch):
    monkeypatch.setattr(embeddings, "_unavailable_until", 0.0)


@pytest.mark.usefixtures("fresh_service")
@pytest.mark.ckan_config("ckan.cioos.embeddings_url", "")
def test_embed_is_disabled_without_a_url(monkeypatch):
    monkeypatch.setattr(requests, "post", pytest.fail)
    assert embeddings.embed("text", 1) is None


@pytest.mark.usefixtures("fresh_service")
@pytest.mark.ckan_config("ckan.cioos.embeddings_url", "http://embeddings")
def test_embed_backs_off_after_a_failure(monkeypatch):
    calls = []

    def failing_post(*args, **kwargs):
        calls.append(args)
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", failing_post)
    assert embeddings.embed("text", 1) is None
    assert embeddings.embed("text", 1) is None
    assert len(calls) == 1


def test_dataset_passage_puts_short_fields_before_the_abstract():
    passage = embeddings.dataset_passage(
        {
            "title_en": "",
            "title_fr": "Phoques annelés",
            "eov": ["marineTurtlesBirdsMammalsAbundanceAndDistribution"],
            "tags_en": ["seals", "Arctic"],
            "organization_en": "Amundsen Science",
            "notes_en": "Long abstract.",
        }
    )
    assert passage == (
        "Phoques annelés. marine turtles birds mammals abundance and distribution. "
        "seals, Arctic. Amundsen Science. Long abstract."
    )
