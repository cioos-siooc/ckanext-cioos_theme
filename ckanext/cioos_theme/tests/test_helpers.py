"""Tests for helpers.py."""

import pytest

from ckanext.cioos_theme.helpers import theme_color_overrides


@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
@pytest.mark.ckan_config("ckan.cioos.accent_color", " #FA7 ")
@pytest.mark.ckan_config("ckan.cioos.footer_color", "#0b1f26")
def test_theme_color_overrides_maps_config_to_tokens():
    assert theme_color_overrides() == {
        "--cioos-primary": "#1b6ca8",
        "--cioos-accent": "#FA7",
        "--cioos-footer-bg": "#0b1f26",
    }


@pytest.mark.ckan_config("ckan.cioos.primary_color", "red;}</style><script>")
@pytest.mark.ckan_config("ckan.cioos.primary_dark_color", "#12345")
def test_theme_color_overrides_drops_non_hex_values():
    assert theme_color_overrides() == {}


@pytest.mark.usefixtures("with_plugins")
@pytest.mark.ckan_config("ckan.cioos.primary_color", "#1b6ca8")
def test_theme_color_overrides_rendered_in_page(app):
    assert ":root { --cioos-primary: #1b6ca8; }" in app.get("/dataset/").body



def _eov(name, category="Physical", count=0):
    return {"name": name, "category": category, "count": count}


def test_eov_categories_orders_categories_and_ranks_by_count():
    from ckanext.cioos_theme.helpers import eov_categories

    groups = eov_categories([
        _eov("oxygen", category="Biogeochemical", count=926),
        _eov("brandNew", category="Aardvark", count=3),
        _eov("seaState", count=29),
        _eov("seaSurfaceTemperature", count=286),
    ])

    # Fixed order first; categories outside it follow alphabetically.
    assert [g["category"] for g in groups] == ["Physical", "Biogeochemical", "Aardvark"]
    assert [x["name"] for x in groups[0]["eovs"]] == ["seaSurfaceTemperature", "seaState"]


def test_eov_categories_applies_exclusions_and_handles_no_counts():
    from ckanext.cioos_theme.helpers import eov_categories

    groups = eov_categories(
        [{"name": "seaState", "category": "Physical"}, _eov("oxygen", category="Biogeochemical"), _eov("seaIce")],
        exclude_eov="['seaIce']",
        exclude_category="Biogeochemical",
    )

    assert groups == [{"category": "Physical", "eovs": [_eov("seaState")]}]
