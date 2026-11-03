"""Tests for the free-text search rewrite (plugin.py)."""

import pytest

from ckanext.cioos_theme.plugin import FIELDED_QUERY_RE, Cioos_ThemePlugin


@pytest.mark.parametrize(
    "q", ["Placentia Bay: North Harbour", '"Prince Rupert"', "kelp -canopy", "temp*"]
)
def test_free_text_query_uses_edismax(q):
    params = {"q": q}
    Cioos_ThemePlugin()._free_text_query(params, q)

    assert params["defType"] == "lucene"
    # q.op=OR scoped to the query, so CKAN's fq keeps its implicit AND
    assert params["q"] == "{!edismax q.op=OR}" + q
    assert params["mm"] == "2<-1 5<80%"


@pytest.mark.parametrize("q", ["id:abc", "tags:Oceans", "harvest_source_id:x AND y"])
def test_fielded_queries_are_detected(q):
    assert FIELDED_QUERY_RE.search(q)


@pytest.mark.parametrize("q", ["Placentia Bay: North Harbour", "sea surface temperature"])
def test_free_text_is_not_fielded(q):
    assert not FIELDED_QUERY_RE.search(q)
